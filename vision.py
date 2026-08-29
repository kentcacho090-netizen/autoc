"""Screen observation for AUTO.

Only lightweight Pillow processing is used in Python. Tesseract is isolated in
its own subprocess so a broken OCR binary cannot crash the controller process.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:  # pragma: no cover - handled at runtime on Android
    Image = None


@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    game_viewport: str = "unknown"
    resources: Dict[str, Optional[int]] = field(default_factory=lambda: {
        "gold": None,
        "elixir": None,
        "dark_elixir": None,
        "builder_gold": None,
        "builder_elixir": None,
        "gems": None,
    })
    text: str = ""
    confidence: float = 0.0
    source: str = "none"
    regions_read: int = 0
    diagnostics: str = ""

    def to_dict(self):
        return asdict(self)


class ScreenDetector:
    """Detect basic CoC HUD state from a screenshot.

    Missing dark elixir/builder resources are normal at lower Town Halls and
    are represented as None rather than causing home-village detection to fail.
    """

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        ocr = self.config.get("ocr", {})
        self.scale = max(2, min(6, int(ocr.get("scale", 4))))
        self.threshold = max(120, min(240, int(ocr.get("threshold", 170))))
        self.ocr_timeout = max(1, min(10, int(ocr.get("timeout", 4))))

    @staticmethod
    def _load_config(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                value = json.load(f)
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError):
            return {}

    def capture(self, filename="autoc_observation.png"):
        return self.controller.take_screenshot(filename)

    @staticmethod
    def parse_number(text):
        if not text:
            return None
        raw = text.strip().upper().replace(" ", "")
        # OCR occasionally adds a punctuation mark. Remove only separators;
        # never silently accept arbitrary letters.
        raw = raw.replace("|", "")
        if not re.fullmatch(r"[0-9][0-9,\.]*[KMB]?", raw):
            return None
        suffix = raw[-1:] if raw[-1:] in "KMB" else ""
        token = raw[:-1] if suffix else raw
        try:
            if suffix:
                token = token.replace(",", "")
                value = float(token) * {"K": 10**3, "M": 10**6, "B": 10**9}[suffix]
                return int(value) if value >= 0 else None
            token = token.replace(",", "").replace(".", "")
            return int(token)
        except (ValueError, OverflowError):
            return None

    @staticmethod
    def _find_game_viewport(image):
        return image, (0, 0, image.width, image.height), "none"

    @staticmethod
    def _crop_norm(image, region):
        x, y, w, h = [float(v) for v in region]
        left = max(0, min(image.width - 1, int(x * image.width)))
        top = max(0, min(image.height - 1, int(y * image.height)))
        right = max(left + 1, min(image.width, int((x + w) * image.width)))
        bottom = max(top + 1, min(image.height, int((y + h) * image.height)))
        return image.crop((left, top, right, bottom))

    def _white_text_mask(self, crop):
        """Extract bright, low-saturation HUD text without OpenCV."""
        rgb = crop.convert("RGB")
        # Enhance contrast first; this is faster and more stable than a Python
        # pixel-by-pixel loop on every screenshot.
        gray = ImageOps.grayscale(rgb)
        gray = ImageEnhance.Contrast(gray).enhance(1.8)
        mask = gray.point(lambda p: 255 if p >= self.threshold else 0)
        return mask.filter(ImageFilter.MaxFilter(3))

    def _tesseract(self, image, psm):
        if Image is None or not shutil.which("tesseract"):
            return ""
        temp = None
        try:
            fd, temp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            image.save(temp, format="PNG", optimize=False)
            result = subprocess.run(
                [
                    "tesseract", temp, "stdout",
                    "--psm", str(psm),
                    "-c", "tessedit_char_whitelist=0123456789KMB",
                    "-c", "user_defined_dpi=200",
                ],
                capture_output=True,
                text=True,
                timeout=self.ocr_timeout,
            )
            # A negative return code means the child was terminated by a
            # signal; report no OCR rather than taking down AUTO.
            if result.returncode != 0:
                return ""
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
        finally:
            if temp:
                try:
                    os.unlink(temp)
                except OSError:
                    pass

    def _resource_number(self, image, region) -> Tuple[Optional[int], str, float]:
        crop = self._crop_norm(image, region)
        mask = self._white_text_mask(crop)
        bbox = mask.getbbox()
        if not bbox:
            return None, "", 0.0

        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if bw < 8 or bh < 5:
            return None, "", 0.0

        pad_x = max(4, int(bw * 0.12))
        pad_y = max(4, int(bh * 0.35))
        x1 = max(0, bbox[0] - pad_x)
        y1 = max(0, bbox[1] - pad_y)
        x2 = min(mask.width, bbox[2] + pad_x)
        y2 = min(mask.height, bbox[3] + pad_y)
        digit_img = mask.crop((x1, y1, x2, y2)).resize(
            ((x2 - x1) * self.scale, (y2 - y1) * self.scale)
        )

        outputs = []
        for psm in (7, 13):
            raw = self._tesseract(digit_img, psm)
            value = self.parse_number(raw)
            if value is not None and 0 <= value <= 2_000_000_000:
                outputs.append((value, raw))

        if not outputs:
            return None, "", 0.0

        # Prefer agreement between independent Tesseract layouts. If they
        # disagree, use the first valid result but lower confidence sharply.
        values = [v for v, _ in outputs]
        if len(values) == 2 and values[0] != values[1]:
            return values[0], outputs[0][1], 0.60

        value, raw = outputs[0]
        return value, raw, 0.95 if len(outputs) == 2 else 0.75

    @staticmethod
    def _default_hud_regions():
        return {
            "gold": [0.835, 0.015, 0.155, 0.075],
            "elixir": [0.835, 0.095, 0.155, 0.075],
            "dark_elixir": [0.835, 0.175, 0.155, 0.075],
            "gems": [0.835, 0.245, 0.155, 0.075],
        }

    def observe(self, image_path=None):
        path = image_path or self.capture()
        if not path or not os.path.exists(path):
            return Observation(source="screenshot_failed")
        if Image is None:
            return Observation(source="pillow_missing")
        if not shutil.which("tesseract"):
            return Observation(source="tesseract_missing")

        try:
            with Image.open(path) as original:
                original.load()
                original = original.convert("RGB")
                width, height = original.size
                game, bounds, rotation = self._find_game_viewport(original)

                regions = self._default_hud_regions()
                configured = self.regions if isinstance(self.regions, dict) else {}
                for key in regions:
                    candidate = configured.get(key)
                    if isinstance(candidate, (list, tuple)) and len(candidate) == 4:
                        regions[key] = list(candidate)

                resources = {
                    "gold": None, "elixir": None, "dark_elixir": None,
                    "builder_gold": None, "builder_elixir": None, "gems": None,
                }
                raw_parts = []
                confs = []
                for key in ("gold", "elixir", "dark_elixir", "gems"):
                    value, raw, conf = self._resource_number(game, regions[key])
                    resources[key] = value
                    if raw:
                        raw_parts.append(f"{key}:{raw}")
                        confs.append(conf)

                core_hits = sum(resources[k] is not None for k in ("gold", "elixir"))
                village = "home" if core_hits == 2 else "unknown"
                confidence = sum(confs) / len(confs) if confs else 0.0
                diagnostics = (
                    f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; "
                    f"rotation={rotation}; resource_regions=calibrated-right; "
                    f"raw=" + " || ".join(raw_parts)
                )
                return Observation(
                    village=village,
                    orientation="landscape" if width > height else "portrait",
                    screen_size=f"{width}x{height}",
                    game_viewport=f"{game.width}x{game.height}",
                    resources=resources,
                    text=" || ".join(raw_parts),
                    confidence=confidence,
                    source="tesseract-white-mask",
                    regions_read=len(raw_parts),
                    diagnostics=diagnostics,
                )
        except (OSError, ValueError, RuntimeError) as exc:
            return Observation(source="image_error", diagnostics=str(exc))
