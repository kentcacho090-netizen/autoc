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
    from PIL import Image
except ImportError:
    Image = None


@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    game_viewport: str = "unknown"
    resources: Dict[str, Optional[int]] = field(
        default_factory=lambda: {
            "gold": None,
            "elixir": None,
            "dark_elixir": None,
            "builder_gold": None,
            "builder_elixir": None,
            "gems": None,
        }
    )
    text: str = ""
    confidence: float = 0.0
    source: str = "none"
    regions_read: int = 0
    diagnostics: str = ""

    def to_dict(self):
        return asdict(self)


class ScreenDetector:
    """Safe CoC OCR for Termux; avoids fixed pixel assumptions beyond HUD regions."""

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        ocr = self.config.get("ocr", {})
        self.scale = max(2, int(ocr.get("scale", 3)))
        self.threshold = int(ocr.get("threshold", 165))

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
        """Parse common CoC resource OCR forms without truncating leading digits.

        Accepted examples include 1234567, 1,234,567, 1.234.567, 1.2M,
        1,2M, and 12K. OCR punctuation is treated as a grouping separator
        for unsuffixed integers and as a decimal separator for suffixed values.
        """
        if not text:
            return None
        raw = str(text).strip().upper()
        raw = raw.replace("O", "0").replace("I", "1").replace("L", "1")
        raw = re.sub(r"\s+", "", raw)
        raw = re.sub(r"[^0-9KMB,\.\-]", "", raw)
        if not raw or raw.startswith("-"):
            return None

        suffix = raw[-1:] if raw[-1:] in "KMB" else ""
        token = raw[:-1] if suffix else raw
        if not token or not re.fullmatch(r"[0-9][0-9,\.]*", token):
            return None

        try:
            if suffix:
                compact = token.replace(",", ".")
                if compact.count(".") > 1:
                    parts = compact.split(".")
                    compact = parts[0] + "." + "".join(parts[1:])
                multiplier = {"K": 10**3, "M": 10**6, "B": 10**9}[suffix]
                return int(round(float(compact) * multiplier))

            digits = re.sub(r"[,.]", "", token)
            return int(digits)
        except (ValueError, OverflowError):
            return None

    @staticmethod
    def _find_game_viewport(image):
        return image, (0, 0, image.width, image.height), "none"

    @staticmethod
    def _crop_norm(image, region):
        x, y, w, h = [float(v) for v in region]
        left = max(0, int(x * image.width))
        top = max(0, int(y * image.height))
        right = min(image.width, int((x + w) * image.width))
        bottom = min(image.height, int((y + h) * image.height))
        if right <= left or bottom <= top:
            return image.crop((0, 0, 1, 1))
        return image.crop((left, top, right, bottom))

    def _white_text_mask(self, crop):
        rgb = crop.convert("RGB")
        width, height = rgb.size
        out = Image.new("L", (width, height), 0)
        src = list(rgb.getdata())
        dst = [0] * (width * height)
        for i, (r, g, b) in enumerate(src):
            hi, lo = max(r, g, b), min(r, g, b)
            if hi >= self.threshold and hi - lo <= 65 and r + g + b >= 520:
                dst[i] = 255
        out.putdata(dst)
        return out

    def _tesseract_candidates(self, image):
        """Return multiple OCR readings so a bad segmentation cannot drop digits."""
        if Image is None or not shutil.which("tesseract"):
            return []
        temp = None
        try:
            fd, temp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            image.save(temp, format="PNG")
            candidates = []
            for psm in (7, 6, 13):
                try:
                    result = subprocess.run(
                        [
                            "tesseract",
                            temp,
                            "stdout",
                            "--psm",
                            str(psm),
                            "-c",
                            "tessedit_char_whitelist=0123456789KMBkmb,.",
                            "-c",
                            "load_system_dawg=0",
                            "-c",
                            "load_freq_dawg=0",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=8,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    continue
                if result.returncode == 0:
                    value = result.stdout.strip()
                    if value:
                        candidates.append(value)
            return candidates
        finally:
            if temp:
                try:
                    os.unlink(temp)
                except OSError:
                    pass

    def _tesseract(self, image):
        candidates = self._tesseract_candidates(image)
        if not candidates:
            return ""
        parsed = [(self.parse_number(value), value) for value in candidates]
        valid = [(number, value) for number, value in parsed if number is not None]
        if valid:
            valid.sort(key=lambda item: (len(re.sub(r"[^0-9]", "", item[1])), len(item[1])), reverse=True)
            return valid[0][1]
        return max(candidates, key=len)

    def _resource_number(self, image, region) -> Tuple[Optional[int], str, float]:
        crop = self._crop_norm(image, region)
        mask = self._white_text_mask(crop)
        bbox = mask.getbbox()
        if not bbox:
            return None, "", 0.0
        bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if bw < 10 or bh < 6:
            return None, "", 0.0
        px, py = max(4, int(bw * 0.10)), max(4, int(bh * 0.35))
        x1, y1 = max(0, bbox[0] - px), max(0, bbox[1] - py)
        x2, y2 = min(mask.width, bbox[2] + px), min(mask.height, bbox[3] + py)
        digit = mask.crop((x1, y1, x2, y2))
        digit = digit.resize(((x2 - x1) * self.scale, (y2 - y1) * self.scale))
        raw = self._tesseract(digit)
        value = self.parse_number(raw)
        if value is not None and 0 <= value <= 2_000_000_000:
            return value, raw, 0.85
        return None, raw, 0.0

    @staticmethod
    def _default_hud_regions():
        return {
            "gold": [0.800, 0.015, 0.185, 0.075],
            "elixir": [0.800, 0.105, 0.185, 0.075],
            "dark_elixir": [0.800, 0.195, 0.185, 0.075],
            "gems": [0.800, 0.285, 0.185, 0.075],
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
                    "gold": None,
                    "elixir": None,
                    "dark_elixir": None,
                    "builder_gold": None,
                    "builder_elixir": None,
                    "gems": None,
                }
                raw_parts = []
                confs = []
                for key in ("gold", "elixir", "dark_elixir", "gems"):
                    value, raw, conf = self._resource_number(game, regions[key])
                    resources[key] = value
                    if raw:
                        raw_parts.append(f"{key}:{raw}")
                    if value is not None:
                        confs.append(conf)

                village = (
                    "home"
                    if resources["gold"] is not None and resources["elixir"] is not None
                    else "unknown"
                )
                confidence = sum(confs) / len(confs) if confs else 0.0
                diagnostics = (
                    f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; "
                    f"rotation={rotation}; resource_regions=wide-right; "
                    f"read={len(raw_parts)}/4; raw=" + " || ".join(raw_parts)
                )
                return Observation(
                    village=village,
                    orientation="landscape" if width > height else "portrait",
                    screen_size=f"{width}x{height}",
                    game_viewport=f"{game.width}x{game.height}",
                    resources=resources,
                    text=" || ".join(raw_parts),
                    confidence=confidence,
                    source="tesseract-white-mask-multipass",
                    regions_read=len(raw_parts),
                    diagnostics=diagnostics,
                )
        except Exception as exc:
            return Observation(source="image_error", diagnostics=str(exc))
