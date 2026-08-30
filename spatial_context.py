"""Spatial correlation for AutoC semantic action gating.

OCR and accessibility text can contain unrelated labels from several UI
regions at once. This module keeps semantic evidence attached to its screen
bounds and only authorizes an object when its evidence overlaps or is close
to the actionable control. No coordinate is synthesized by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional, Sequence

from action_gate import SelectionContext
from automation_state import Target
from selection_context import SEMANTIC_LABELS, SemanticLabel


@dataclass(frozen=True)
class SpatialEvidence:
    """A semantic label with the screen region that produced it."""

    text: str
    bounds: tuple[int, int, int, int]
    source: str = "unknown"
    confidence: float = 1.0

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx = float(a[0] - b[0])
    dy = float(a[1] - b[1])
    return (dx * dx + dy * dy) ** 0.5


def _gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx = max(bx1 - ax2, ax1 - bx2, 0)
    dy = max(by1 - ay2, ay1 - by2, 0)
    return (float(dx * dx + dy * dy)) ** 0.5


class SpatialContextDetector:
    """Correlate semantic labels with an actionable target conservatively."""

    def __init__(
        self,
        labels: Iterable[SemanticLabel] = SEMANTIC_LABELS,
        max_gap_pixels: int = 220,
    ) -> None:
        self.labels = tuple(labels)
        self.max_gap_pixels = max(1, int(max_gap_pixels))

    def _label_for(self, text: str) -> Optional[SemanticLabel]:
        normalized = _normalize(text)
        if not normalized:
            return None
        matches = [
            label
            for label in self.labels
            if any(_normalize(alias) in normalized for alias in label.aliases)
        ]
        if not matches:
            return None
        return max(matches, key=lambda label: max(len(_normalize(a)) for a in label.aliases))

    def identify(
        self,
        action_name: str,
        target: Optional[Target],
        evidence: Sequence[SpatialEvidence],
        village: str,
        observation_confidence: float,
    ) -> Optional[SelectionContext]:
        if target is None or observation_confidence <= 0.0:
            return None
        required_feature = {
            "hero_upgrade": "hero",
            "laboratory": "laboratory",
            "builder_lab": "builder_laboratory",
            "wall_upgrade": "wall",
            "builder_wall_upgrade": "builder_wall",
            "building_upgrade": "building",
            "builder_upgrade": "builder_building",
        }.get(action_name)
        if required_feature is None:
            return None

        target_bounds = (
            target.center[0],
            target.center[1],
            target.center[0],
            target.center[1],
        )
        candidates: list[tuple[float, SemanticLabel, SpatialEvidence]] = []
        for item in evidence:
            if item.confidence <= 0.0:
                continue
            label = self._label_for(item.text)
            if label is None:
                continue
            compatible = label.feature == required_feature or (
                required_feature in {"builder_laboratory", "builder_wall", "builder_building"}
                and label.feature == required_feature.removeprefix("builder_")
            )
            if not compatible:
                continue
            gap = _gap(item.bounds, target_bounds)
            distance = _distance(item.center, target.center)
            if gap > self.max_gap_pixels and distance > self.max_gap_pixels:
                continue
            score = item.confidence * target.confidence * (1.0 / (1.0 + gap + distance / 4.0))
            candidates.append((score, label, item))

        if not candidates:
            return None
        _, selected, item = max(candidates, key=lambda value: value[0])
        features = {selected.feature, selected.name.replace(" ", "_")}
        if action_name == "builder_lab":
            features.add("builder_laboratory")
        elif action_name == "builder_wall_upgrade":
            features.add("builder_wall")
        elif action_name == "builder_upgrade":
            features.add("builder_building")

        return SelectionContext(
            object_type=selected.feature,
            object_name=selected.name,
            village=village,
            source=item.source,
            confidence=min(float(observation_confidence), target.confidence, item.confidence),
            features=frozenset(features),
        )
