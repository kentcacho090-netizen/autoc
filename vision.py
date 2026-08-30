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

try:
    from resource_observer import DynamicResourceObserver
except ImportError:
    DynamicResourceObserver = None


@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    game_viewport: str = "unknown"
    town_hall: Optional[int] = None
    town_hall_confidence: float = 0.0
    builder_base_unlocked: bool = False
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
    """Observe the current CoC screen with screenshot OCR and dynamic resource geometry."""

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        self.regions = self.config.get("regions", {})
        ocr = self.config.get("ocr", {})
        self.scale = max(2, int(ocr.get("scale", 3)))
        self.threshold = int(ocr.get("threshold", 165))
        self.resource_observer = DynamicResourceObserver() if DynamicResourceObserver is not None else None

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
        raw = str(text).strip().upper().replace("O", "0").replace("I", "1").replace("L", "1")
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
                return int(round(float(compact) * {"K": 10**3, "M": 10**6, "B": 10**9}[suffix]))
            return int(re.sub(r"[,.]", "", token))
        except (ValueError, OverflowError):
            return None

    def _dynamic_resources(self, image_path):
        if self.resource_observer is None:
            return None
        try:
            return self.resource_observer.read(image_path)
        except Exception:
            return None

    @staticmethod
    def _find_game_viewport(image):
        return image, (0, 0, image.width, image.height), "none"

    def observe(self, image_path=None):
        path = image_path or self.capture()
        if not path or not os.path.exists(path):
            return Observation(source="screenshot_failed")
        if Image is None:
            return Observation(source="pillow_missing")
        try:
            with Image.open(path) as original:
                original = original.convert("RGB")
                width, height = original.size
                game, bounds, rotation = self._find_game_viewport(original)
                dynamic = self._dynamic_resources(path)
                if dynamic is not None:
                    resources = {
                        "gold": dynamic.values.get("gold"),
                        "elixir": dynamic.values.get("elixir"),
                        "dark_elixir": dynamic.values.get("dark_elixir"),
                        "builder_gold": None,
                        "builder_elixir": None,
                        "gems": dynamic.values.get("gems"),
                    }
                    readable = sum(value is not None for value in resources.values())
                    confidence_values = [value for value in dynamic.confidence.values() if value > 0]
                    confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
                    village = "home" if resources["gold"] is not None and resources["elixir"] is not None else "unknown"
                    raw_parts = [
                        f"{candidate.raw}@({candidate.x},{candidate.y})"
                        for candidate in dynamic.candidates[:12]
                    ]
                    return Observation(
                        village=village,
                        orientation="landscape" if width > height else "portrait",
                        screen_size=f"{width}x{height}",
                        game_viewport=f"{game.width}x{game.height}",
                        resources=resources,
                        text=" || ".join(raw_parts),
                        confidence=confidence,
                        source=dynamic.source,
                        regions_read=readable,
                        diagnostics=f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; rotation={rotation}; dynamic_resource_candidates={len(dynamic.candidates)}; readable={readable}/6",
                    )
                return Observation(
                    village="unknown",
                    orientation="landscape" if width > height else "portrait",
                    screen_size=f"{width}x{height}",
                    game_viewport=f"{game.width}x{game.height}",
                    source="no-resource-observer",
                    diagnostics="Dynamic resource observer unavailable",
                )
        except Exception as exc:
            return Observation(source="image_error", diagnostics=str(exc))
