"""Screen observation layer for AutoC.

Turns Android screenshots into conservative structured observations. Game
specific actions should only run after the required state is confirmed.
"""
from dataclasses import dataclass, field, asdict
import json
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
    regions_read: int = 0

    def to_dict(self):
        return asdict(self)


class ScreenDetector:
    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.7))
        ocr = self.config.get("ocr", {})
        self.scale = max(1, int(ocr.get("scale", 3)))
        self.psm = int(ocr.get("psm", 7))

    @staticmethod
    def _load_config(path):
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def capture(self, filename="autoc_observation.png"):
        return self.controller.take_screenshot(filename)

    def _read_region(self, image, region) -> str:
        if cv2 is None or pytesseract is None:
            return ""
        x, y, w, h = [int(v) for v in region]
        if w <= 0 or h <= 0:
            return ""
        crop = image[max(0, y):max(0, y + h), max(0, x):max(0, x + w)]
        if crop.size == 0:
            return ""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return pytesseract.image_to_string(threshold, config=f"--psm {self.psm}").strip()

    @staticmethod
    def parse_number(text: str):
        if not text:
            return None
        cleaned = text.upper().replace("O", "0").replace("I", "1").replace("L", "1")
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
                texts[name] = self._read_region(image, region)

        aliases = {
            "gold": ("gold", "home_gold"),
            "elixir": ("elixir", "home_elixir"),
            "dark_elixir": ("dark_elixir", "de"),
            "builder_gold": ("builder_gold", "bb_gold"),
            "builder_elixir": ("builder_elixir", "bb_elixir"),
        }
        resources = {k: next((self.parse_number(texts[n]) for n in names if texts.get(n)), None)
                     for k, names in aliases.items()}

        home_hits = sum(resources[k] is not None for k in ("gold", "elixir", "dark_elixir"))
        bb_hits = sum(resources[k] is not None for k in ("builder_gold", "builder_elixir"))
        if bb_hits > home_hits:
            village = "builder_base"
        elif home_hits:
            village = "home"
        else:
            village = "unknown"

        configured = len(texts)
        readable = sum(bool(v) for v in texts.values())
        confidence = min(1.0, readable / max(1, configured))
        return Observation(village=village, resources=resources,
                           text=" ".join(v for v in texts.values() if v),
                           confidence=confidence, source="ocr", regions_read=readable)
