"""Android screenshot observation using native Termux OCR."""
from dataclasses import dataclass, field, asdict
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
except ImportError:
    Image = None


@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    game_viewport: str = "unknown"
    resources: Dict[str, Optional[int]] = field(default_factory=lambda: {
        "gold": None, "elixir": None, "dark_elixir": None,
        "builder_gold": None, "builder_elixir": None, "gems": None,
    })
    text: str = ""
    confidence: float = 0.0
    source: str = "none"
    regions_read: int = 0
    diagnostics: str = ""

    def to_dict(self):
        return asdict(self)


class ScreenDetector:
    """CoC resource OCR for a 1280x720 landscape screenshot.

    The resource digits are on the far-right side of the HUD. The detector
    uses wider crops so the first digit is not clipped. Dark elixir and gems
    are separate HUD rows; on low Town Halls dark elixir is absent, which is
    valid and must not make the whole home-village detection fail.
    """

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        ocr = self.config.get("ocr", {})
        self.scale = max(2, int(ocr.get("scale", 4)))
        self.threshold = int(ocr.get("threshold", 180))

    @staticmethod
    def _load_config(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def capture(self, filename="autoc_observation.png"):
        return self.controller.take_screenshot(filename)

    @staticmethod
    def parse_number(text):
        if not text:
            return None
        raw = text.strip().upper().replace(" ", "")
        if not re.fullmatch(r"[0-9][0-9,\.]*[KMB]?", raw):
            return None
        suffix = raw[-1:] if raw[-1:] in "KMB" else ""
        token = raw[:-1] if suffix else raw
        if suffix:
            token = token.replace(",", "")
            try:
                return int(float(token) * {"K": 10**3, "M": 10**6, "B": 10**9}[suffix])
            except ValueError:
                return None
        token = token.replace(",", "").replace(".", "")
        try:
            return int(token)
        except ValueError:
            return None

    @staticmethod
    def _find_game_viewport(image):
        w, h = image.size
        return image, (0, 0, w, h), "none"

    @staticmethod
    def _crop_norm(image, region):
        x, y, w, h = [float(v) for v in region]
        left = max(0, int(x * image.width))
        top = max(0, int(y * image.height))
        right = min(image.width, int((x + w) * image.width))
        bottom = min(image.height, int((y + h) * image.height))
        return image.crop((left, top, right, bottom))

    def _white_text_mask(self, crop):
        rgb = crop.convert("RGB")
        px = rgb.load()
        out = Image.new("L", rgb.size, 0)
        opx = out.load()
        threshold = self.threshold
        for y in range(rgb.height):
            for x in range(rgb.width):
                r, g, b = px[x, y]
                hi = max(r, g, b)
                lo = min(r, g, b)
                if hi >= threshold and (hi - lo) <= 55 and (r + g + b) >= 560:
                    opx[x, y] = 255
        out = out.filter(ImageFilter.MaxFilter(3))
        out = out.filter(ImageFilter.MedianFilter(3))
        return out

    def _tesseract(self, image, psm):
        if Image is None or not shutil.which("tesseract"):
            return ""
        temp = None
        try:
            fd, temp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            image.save(temp)
            result = subprocess.run(
                [
                    "tesseract", temp, "stdout", "--psm", str(psm),
                    "-c", "tessedit_char_whitelist=0123456789KMB",
                ],
                capture_output=True, text=True, timeout=12,
            )
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
        if bw < 10 or bh < 6:
            return None, "", 0.0

        pad_x = max(3, int(bw * 0.08))
        pad_y = max(3, int(bh * 0.30))
        x1 = max(0, bbox[0] - pad_x)
        y1 = max(0, bbox[1] - pad_y)
        x2 = min(mask.width, bbox[2] + pad_x)
        y2 = min(mask.height, bbox[3] + pad_y)
        digit_img = mask.crop((x1, y1, x2, y2)).resize(
            ((x2 - x1) * self.scale, (y2 - y1) * self.scale)
        )

        outputs = []
        for psm in (7, 8, 13):
            raw = self._tesseract(digit_img, psm)
            value = self.parse_number(raw)
            if value is not None and 0 <= value <= 2_000_000_000:
                outputs.append((value, raw))

        if not outputs:
            return None, "", 0.0

        counts = {}
        for value, raw in outputs:
            counts[value] = counts.get(value, 0) + 1
        best_value = max(counts, key=lambda v: (counts[v], -len(str(v))))
        agreeing = counts[best_value]
        confidence = min(0.99, 0.55 + 0.20 * agreeing)
        raw_text = " | ".join(raw for value, raw in outputs if value == best_value)
        return best_value, raw_text, confidence

    @staticmethod
    def _default_hud_regions():
        # Calibrated against the supplied 1280x720 landscape home-village
        # screenshot: gold ~y=0.04, elixir ~0.14, gems ~0.23. Crops extend
        # left far enough to include the first digit (e.g. 7832).
        return {
            "gold": [0.850, 0.015, 0.135, 0.075],
            "elixir": [0.850, 0.105, 0.135, 0.075],
            "dark_elixir": [0.850, 0.195, 0.135, 0.075],
            "gems": [0.850, 0.210, 0.135, 0.075],
        }

    def observe(self, image_path=None):
        path = image_path or self.capture()
        if not path or not os.path.exists(path):
            return Observation(source="screenshot_failed")
        if not shutil.which("tesseract"):
            return Observation(source="tesseract_missing")
        if Image is None:
            return Observation(source="pillow_missing")

        try:
            with Image.open(path) as original:
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
                raw_parts, confs = [], []
                for key in ("gold", "elixir", "dark_elixir", "gems"):
                    value, raw, conf = self._resource_number(game, regions[key])
                    resources[key] = value
                    if raw:
                        raw_parts.append(f"{key}:{raw}")
                        confs.append(conf)

                # Dark elixir does not exist before the Town Hall unlock.
                # Require gold + elixir for home-village identification.
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
        except Exception as exc:
            return Observation(source="image_error", diagnostics=str(exc))
