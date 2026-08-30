"""Dynamic screenshot observation for AutoC."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import json
import os
import re
from typing import Dict, Optional

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from resource_observer import DynamicResourceObserver
except ImportError:
    DynamicResourceObserver = None

try:
    from feature_unlocks import FeatureUnlockDetector
except ImportError:
    FeatureUnlockDetector = None


@dataclass
class Observation:
    village: str = "unknown"
    orientation: str = "unknown"
    screen_size: str = "unknown"
    game_viewport: str = "unknown"
    town_hall: Optional[int] = None
    town_hall_confidence: float = 0.0
    builder_base_unlocked: bool = False
    dark_elixir_unlocked: bool = False
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
    """Observe CoC from fresh screenshots; absence never unlocks optional systems."""

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        ocr = self.config.get("ocr", {})
        self.scale = max(2, int(ocr.get("scale", 3)))
        self.threshold = int(ocr.get("threshold", 165))
        self.resource_observer = DynamicResourceObserver() if DynamicResourceObserver else None
        self.feature_detector = FeatureUnlockDetector() if FeatureUnlockDetector else None

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

    @staticmethod
    def _normalize(text):
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    @staticmethod
    def _town_hall_from_text(text):
        normalized = ScreenDetector._normalize(text)
        for pattern in (
            r"town\s*hall\s*(?:level\s*)?(\d{1,2})",
            r"townhall\s*(?:level\s*)?(\d{1,2})",
            r"\bth\s*(?:level\s*)?(\d{1,2})\b",
        ):
            match = re.search(pattern, normalized)
            if match:
                level = int(match.group(1))
                if 1 <= level <= 20:
                    return level, 0.98
        return None, 0.0

    def _dynamic_resources(self, image_path):
        if self.resource_observer is None:
            return None
        try:
            return self.resource_observer.read(image_path)
        except Exception:
            return None

    def _optional_features(self, text):
        if self.feature_detector is None:
            return None
        try:
            return self.feature_detector.detect(ocr_text=text)
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
                resources = {
                    "gold": None,
                    "elixir": None,
                    "dark_elixir": None,
                    "builder_gold": None,
                    "builder_elixir": None,
                    "gems": None,
                }
                text_parts = []
                source = "ocr"
                resource_confidence = []
                regions_read = 0
                if dynamic is not None:
                    resources["gold"] = dynamic.values.get("gold")
                    resources["elixir"] = dynamic.values.get("elixir")
                    resources["dark_elixir"] = dynamic.values.get("dark_elixir")
                    resources["gems"] = dynamic.values.get("gems")
                    regions_read = sum(value is not None for value in resources.values())
                    resource_confidence = [v for v in dynamic.confidence.values() if v > 0]
                    text_parts.extend(
                        f"{candidate.raw}@({candidate.x},{candidate.y})"
                        for candidate in dynamic.candidates[:20]
                    )
                    source = dynamic.source

                text = " || ".join(text_parts)
                town_hall, town_confidence = self._town_hall_from_text(text)
                optional = self._optional_features(text)
                dark_unlocked = bool(optional and optional.dark_elixir_unlocked)
                builder_unlocked = bool(optional and optional.builder_base_unlocked)

                if builder_unlocked:
                    village = "builder_base"
                elif resources["gold"] is not None and resources["elixir"] is not None:
                    village = "home"
                else:
                    village = "unknown"

                confidence_values = resource_confidence[:]
                if town_confidence:
                    confidence_values.append(town_confidence)
                confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
                return Observation(
                    village=village,
                    orientation="landscape" if width > height else "portrait",
                    screen_size=f"{width}x{height}",
                    game_viewport=f"{game.width}x{game.height}",
                    town_hall=town_hall,
                    town_hall_confidence=town_confidence,
                    builder_base_unlocked=builder_unlocked,
                    dark_elixir_unlocked=dark_unlocked,
                    resources=resources,
                    text=text,
                    confidence=confidence,
                    source=source,
                    regions_read=regions_read,
                    diagnostics=(
                        f"viewport={bounds[0]},{bounds[1]}-{bounds[2]},{bounds[3]}; "
                        f"rotation={rotation}; dynamic_resource_candidates="
                        f"{len(dynamic.candidates) if dynamic is not None else 0}; "
                        f"optional_features=explicit-evidence"
                    ),
                )
        except (OSError, ValueError) as exc:
            return Observation(source="image_error", diagnostics=str(exc))
