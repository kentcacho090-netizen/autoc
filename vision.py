"""Screen observation layer for AutoC.

This module turns an Android screenshot into structured observations. It is
intentionally conservative: values are only marked as detected when OCR and
region configuration provide evidence. No game state is guessed.
"""
from dataclasses import dataclass, field, asdict
import os
import re
from typing import Dict, Optional, Tuple

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


@dataclass
class Observation:
    village: str = "unknown"
    resources: Dict[str, Optional[int]] = field(default_factory=lambda: {
        "gold": None, "elixir": None, "dark_elixir": None,
        "builder_gold": None, "builder_elixir": None,
    })
    text: str = ""
    confidence: float = 0.0
    source: str = "none"

    def to_dict(self):
        return asdict(self)


class ScreenDetector:
    """Capture/OCR helper with configurable screen regions."""

    def __init__(self, controller, regions=None):
        self.controller = controller
        self.regions = regions or {}

    def capture(self, filename="autoc_observation.png"):
        return self.controller.take_screenshot(filename)

    def _read_region(self, image, region: Tuple[int, int, int, int]) -> str:
        if cv2 is None or pytesseract is None:
            return ""
        x, y, w, h = [int(v) for v in region]
        crop = image[max(0, y):max(0, y) + max(1, h),
                     max(0, x):max(0, x) + max(1, w)]
        if crop.size == 0:
            return ""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return pytesseract.image_to_string(threshold, config="--psm 7").strip()

    @staticmethod
    def parse_number(text: str):
        if not text:
            return None
        cleaned = text.upper().replace("O", "0").replace("I", "1").replace("L", "1")
        match = re.search(r"\d[\d,\.]*\s*[KMB]?", cleaned)
        if not match:
            return None
        token = match.group(0).replace(",", "").replace(" ", "")
        multiplier = 1
        suffix = token[-1:] if token else ""
        if suffix in "KMB":
            token = token[:-1]
            multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
        try:
            return int(float(token) * multiplier)
        except ValueError:
            return None

    def observe(self, image_path=None) -> Observation:
        path = image_path or self.capture()
        if not path or not os.path.exists(path):
            return Observation(source="screenshot_failed")
        if cv2 is None or pytesseract is None:
            return Observation(source="ocr_dependencies_missing")

        image = cv2.imread(path)
        if image is None:
            return Observation(source="image_failed")

        texts = {}
        for name, region in self.regions.items():
            if isinstance(region, (list, tuple)) and len(region) == 4:
                texts[name] = self._read_region(image, tuple(region))

        full_text = " ".join(v for v in texts.values() if v)
        resources = {}
        aliases = {
            "gold": ("gold", "home_gold"),
            "elixir": ("elixir", "home_elixir"),
            "dark_elixir": ("dark_elixir", "de"),
            "builder_gold": ("builder_gold", "bb_gold"),
            "builder_elixir": ("builder_elixir", "bb_elixir"),
        }
        for resource, names in aliases.items():
            value = next((self.parse_number(texts[n]) for n in names if n in texts), None)
            resources[resource] = value

        village = "unknown"
        if any(k in texts for k in ("builder_gold", "builder_elixir", "bb_gold", "bb_elixir")):
            village = "builder_base"
        elif any(k in texts for k in ("gold", "elixir", "dark_elixir", "home_gold", "home_elixir", "de")):
            village = "home"

        configured = len(texts)
        confidence = min(1.0, configured / 5.0) if configured else 0.0
        return Observation(village=village, resources=resources, text=full_text,
                           confidence=confidence, source="ocr")
