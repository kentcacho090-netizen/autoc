"""Android screenshot observation using native Termux OCR."""
from dataclasses import dataclass, field, asdict
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, Optional

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter
except ImportError:
    Image = None


@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    resources: Dict[str, Optional[int]] = field(default_factory=lambda: {
        "gold": None, "elixir": None, "dark_elixir": None,
        "builder_gold": None, "builder_elixir": None,
    })
    text: str = ""
    confidence: float = 0.0
    source: str = "none"
    regions_read: int = 0
    diagnostics: str = ""

    def to_dict(self):
        return asdict(self)


class ScreenDetector:
    """Capture screenshots and OCR game HUD regions with native Termux tesseract."""

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        ocr = self.config.get("ocr", {})
        self.psm = int(ocr.get("psm", 7))
        self.scale = max(1, int(ocr.get("scale", 3)))

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
    def _screen_geometry(image_path):
        with Image.open(image_path) as image:
            width, height = image.size
        if width > height:
            orientation = "landscape"
        elif height > width:
            orientation = "portrait"
        else:
            orientation = "square"
        return width, height, orientation

    @staticmethod
    def parse_number(text: str):
        if not text:
            return None
        cleaned = text.upper()
        cleaned = cleaned.replace("O", "0").replace("I", "1").replace("L", "1")
        cleaned = cleaned.replace("S", "5").replace("B", "8")
        match = re.search(r"\d[\d,\.]*\s*[KMB]?", cleaned)
        if not match:
            return None
        token = match.group(0).replace(",", "").replace(" ", "")
        suffix = token[-1:] if token else ""
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
        if suffix in "KMB":
            token = token[:-1]
        try:
            return int(float(token) * multiplier)
        except ValueError:
            return None

    def _read_region(self, image_path, region=None):
        if not shutil.which("tesseract"):
            return ""
        source = image_path
        temporary = None
        try:
            if region and Image is not None:
                image = Image.open(image_path).convert("RGB")
                x, y, w, h = [int(v) for v in region]
                crop = image.crop((max(0, x), max(0, y), min(image.width, x + w), min(image.height, y + h)))
                gray = ImageOps.grayscale(crop)
                gray = ImageEnhance.Contrast(gray).enhance(2.5)
                gray = gray.filter(ImageFilter.SHARPEN)
                gray = gray.resize((max(1, gray.width * self.scale), max(1, gray.height * self.scale)))
                fd, temporary = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                gray.save(temporary)
                source = temporary

            # Try the configured mode first, then a single-line mode for HUD counters.
            outputs = []
            for psm in (self.psm, 6, 7, 11):
                result = subprocess.run(
                    ["tesseract", source, "stdout", "--psm", str(psm), "-c", "tessedit_char_whitelist=0123456789KMBkmb,."],
                    capture_output=True, text=True, timeout=15,
                )
                text = result.stdout.strip()
                if text:
                    outputs.append(text)
            return " | ".join(dict.fromkeys(outputs))
        except (OSError, subprocess.SubprocessError):
            return ""
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _dynamic_regions(self, width, height):
        """Return percentage-based HUD candidates; works across landscape resolutions."""
        if width >= height:
            # The observed cloud-phone game is landscape. Counters are normally on the
            # upper-right HUD. Keep several overlapping candidates so calibration can
            # discover which one gives readable text without hard-coding a resolution.
            return {
                "hud_top": [int(width * 0.73), 0, int(width * 0.27), int(height * 0.22)],
                "hud_right": [int(width * 0.78), 0, int(width * 0.22), int(height * 0.42)],
                "hud_right_wide": [int(width * 0.65), 0, int(width * 0.35), int(height * 0.35)],
            }
        return {
            "hud_top": [int(width * 0.60), 0, int(width * 0.40), int(height * 0.18)],
            "hud_right": [int(width * 0.70), 0, int(width * 0.30), int(height * 0.35)],
            "hud_right_wide": [int(width * 0.55), 0, int(width * 0.45), int(height * 0.30)],
        }

    def observe(self, image_path=None) -> Observation:
        path = image_path or self.capture()
        if not path or not os.path.exists(path):
            return Observation(source="screenshot_failed")
        if not shutil.which("tesseract"):
            return Observation(source="tesseract_missing")
        if Image is None:
            return Observation(source="pillow_missing")

        try:
            width, height, orientation = self._screen_geometry(path)
        except Exception as exc:
            return Observation(source="image_error", diagnostics=str(exc))

        configured = dict(self.regions)
        configured.update(self._dynamic_regions(width, height))
        texts = {}
        for name, region in configured.items():
            if isinstance(region, (list, tuple)) and len(region) == 4:
                texts[name] = self._read_region(path, region)

        # Prefer explicitly configured semantic regions. Dynamic HUD OCR is retained as
        # diagnostic text until we have a calibrated mapping for this device/game layout.
        aliases = {
            "gold": ("gold", "home_gold"),
            "elixir": ("elixir", "home_elixir"),
            "dark_elixir": ("dark_elixir", "de"),
            "builder_gold": ("builder_gold", "bb_gold"),
            "builder_elixir": ("builder_elixir", "bb_elixir"),
        }
        resources = {
            key: next((self.parse_number(texts[name]) for name in names if texts.get(name)), None)
            for key, names in aliases.items()
        }

        home_hits = sum(resources[k] is not None for k in ("gold", "elixir", "dark_elixir"))
        bb_hits = sum(resources[k] is not None for k in ("builder_gold", "builder_elixir"))
        if bb_hits > home_hits:
            village = "builder_base"
        elif home_hits:
            village = "home"
        else:
            village = "unknown"

        dynamic_text = " ".join(texts.get(k, "") for k in ("hud_top", "hud_right", "hud_right_wide") if texts.get(k))
        configured_names = [k for k in self.regions if isinstance(self.regions.get(k), (list, tuple))]
        readable = sum(bool(texts.get(k)) for k in configured_names)
        confidence = min(1.0, readable / max(1, len(configured_names)))
        diagnostics = f"dynamic_hud={dynamic_text[:500]}" if dynamic_text else "dynamic_hud=(none)"

        return Observation(
            village=village,
            orientation=orientation,
            screen_size=f"{width}x{height}",
            resources=resources,
            text=" ".join(v for v in texts.values() if v),
            confidence=confidence,
            source="tesseract",
            regions_read=readable,
            diagnostics=diagnostics,
        )
