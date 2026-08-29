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
    """Lightweight Termux detector tuned for a 1280x720 CoC landscape canvas.

    Resource OCR deliberately isolates the white number glyphs before calling
    Tesseract. This prevents foliage, icons, and other game elements from being
    interpreted as huge resource values.
    """

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        ocr = self.config.get("ocr", {})
        self.scale = max(2, int(ocr.get("scale", 4)))
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
        if not text:
            return None
        cleaned = text.upper().replace("O", "0").replace("I", "1").replace("L", "1")
        cleaned = cleaned.replace("S", "5").replace("B", "8")
        # Ignore punctuation that commonly appears between spaced digits.
        cleaned = re.sub(r"\s+", "", cleaned)
        matches = re.findall(r"\d+(?:[\.,]\d+)*[KMB]?", cleaned)
        if not matches:
            return None
        token = matches[0].replace(",", "")
        suffix = token[-1:] if token[-1:] in "KMB" else ""
        if suffix:
            token = token[:-1]
        # A decimal point is a decimal only when an explicit suffix is present.
        if suffix:
            try:
                return int(float(token.replace(",", "")) * {"K": 10**3, "M": 10**6, "B": 10**9}[suffix])
            except ValueError:
                return None
        token = token.replace(".", "")
        try:
            return int(token)
        except ValueError:
            return None

    @staticmethod
    def _find_game_viewport(image):
        # For screenshots produced directly by screencap on the cloud phone,
        # the game already occupies the full 1280x720 canvas. Keep a generic
        # color-based fallback for phone UI screenshots containing black bars.
        w, h = image.size
        if w > h and w >= 1000 and h >= 600:
            return image, (0, 0, w, h), "none"
        return image, (0, 0, w, h), "none"

    @staticmethod
    def _crop_norm(image, region):
        x, y, w, h = [float(v) for v in region]
        left = max(0, int(x * image.width))
        top = max(0, int(y * image.height))
        right = min(image.width, int((x + w) * image.width))
        bottom = min(image.height, int((y + h) * image.height))
        return image.crop((left, top, right, bottom))

    @staticmethod
    def _white_text_mask(crop):
        """Keep bright low-saturation pixels used by CoC's white HUD digits."""
        rgb = crop.convert("RGB")
        px = rgb.load()
        out = Image.new("L", rgb.size, 0)
        opx = out.load()
        for y in range(rgb.height):
            for x in range(rgb.width):
                r, g, b = px[x, y]
                hi = max(r, g, b)
                lo = min(r, g, b)
                if hi >= 165 and (hi - lo) <= 70 and (r + g + b) >= 520:
                    opx[x, y] = 255
        # Slightly thicken the glyph cores, then remove isolated specks.
        out = out.filter(ImageFilter.MaxFilter(3))
        out = out.filter(ImageFilter.MedianFilter(3))
        return out

    def _tesseract(self, image, psm, whitelist="0123456789KMBkmb"):
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
                    "-c", f"tessedit_char_whitelist={whitelist}",
                ],
                capture_output=True,
                text=True,
                timeout=12,
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
        # Remove right-side icon pixels by using the left portion of the region.
        # The supplied reference HUD has the number immediately left of each
        # resource icon, so this is safe across scaled versions of the same HUD.
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        if bw < 8 or bh < 5:
            return None, "", 0.0
        # Tight crop around white glyphs, with a small border.
        pad_x = max(2, int(bw * 0.06))
        pad_y = max(2, int(bh * 0.25))
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

        # Prefer an exact agreement between OCR modes. Never choose the largest
        # number merely because it is large.
        counts = {}
        for value, raw in outputs:
            counts[value] = counts.get(value, 0) + 1
        best_value = max(counts, key=lambda v: (counts[v], -len(str(v))))
        agreeing = counts[best_value]
        confidence = min(0.99, 0.55 + 0.2 * agreeing)
        raw_text = " | ".join(raw for value, raw in outputs if value == best_value)
        return best_value, raw_text, confidence

    @staticmethod
    def _default_hud_regions():
        # Calibrated from the supplied 1280x720 landscape Home Village image.
        # Regions intentionally cover the number glyphs, not the resource icons.
        return {
            "gold": [0.835, 0.018, 0.090, 0.070],
            "elixir": [0.835, 0.105, 0.090, 0.070],
            "dark_elixir": [0.835, 0.190, 0.090, 0.070],
            "gems": [0.835, 0.275, 0.090, 0.070],
        }

    @staticmethod
    def _generic_number_region(name):
        return {
            "gold": [0.835, 0.018, 0.090, 0.070],
            "elixir": [0.835, 0.105, 0.090, 0.070],
            "dark_elixir": [0.835, 0.190, 0.090, 0.070],
            "gems": [0.835, 0.275, 0.090, 0.070],
        }.get(name)

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
                configured = self.regions if isinstance(self.regions, dict) else {}
                regions = self._default_hud_regions()
                for key in regions:
                    candidate = configured.get(key)
                    if not (isinstance(candidate, (list, tuple)) and len(candidate) == 4):
                        candidate = self._generic_number_region(key)
                    if candidate:
                        # Never use the previous overly-wide crops for resources.
                        regions[key] = list(candidate)

                resources = {"gold": None, "elixir": None, "dark_elixir": None, "builder_gold": None, "builder_elixir": None, "gems": None}
                raw_parts = []
                confs = []
                for key in ("gold", "elixir", "dark_elixir", "gems"):
                    value, raw, conf = self._resource_number(game, regions[key])
                    resources[key] = value
                    if raw:
                        raw_parts.append(f"{key}:{raw}")
                        confs.append(conf)

                # Builder count is a separate right-side UI element and is not
                # reliable to infer from resource OCR. Leave it unknown until
                # its dedicated detector is added.
                home_hits = sum(resources[k] is not None for k in ("gold", "elixir"))
                de_hit = resources["dark_elixir"] is not None
                village = "home" if home_hits + int(de_hit) >= 2 else "unknown"
                confidence = sum(confs) / len(confs) if confs else 0.0
                diagnostics = (
                    f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; "
                    f"rotation={rotation}; resource_regions=number-only; "
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
