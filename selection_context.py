"""Semantic selection-context detection for safe AutoC actions.

The detector converts fresh accessibility/OCR evidence into a conservative
selection context. It never invents a building name from an Upgrade button.
A context is returned only when a semantic object label is independently
visible near the actionable control or exposed by the accessibility tree.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from action_gate import SelectionContext
from automation_state import Target


@dataclass(frozen=True)
class SemanticLabel:
    name: str
    aliases: tuple[str, ...]
    feature: str


SEMANTIC_LABELS: tuple[SemanticLabel, ...] = (
    SemanticLabel("laboratory", ("laboratory", "research"), "laboratory"),
    SemanticLabel("hero", ("hero", "barbarian king", "archer queen", "grand warden", "royal champion"), "hero"),
    SemanticLabel("wall", ("wall", "walls"), "wall"),
    SemanticLabel("cannon", ("cannon",), "building"),
    SemanticLabel("archer tower", ("archer tower",), "building"),
    SemanticLabel("wizard tower", ("wizard tower",), "building"),
    SemanticLabel("air defense", ("air defense",), "building"),
    SemanticLabel("mortar", ("mortar",), "building"),
    SemanticLabel("air sweeper", ("air sweeper",), "building"),
    SemanticLabel("bomb tower", ("bomb tower",), "building"),
    SemanticLabel("inferno tower", ("inferno tower",), "building"),
    SemanticLabel("x-bow", ("x-bow", "xbow"), "building"),
    SemanticLabel("tesla", ("hidden tesla", "tesla"), "building"),
    SemanticLabel("spell tower", ("spell tower",), "building"),
    SemanticLabel("monolith", ("monolith",), "building"),
    SemanticLabel("builder hut", ("builder hut",), "building"),
    SemanticLabel("town hall", ("town hall", "townhall"), "building"),
    SemanticLabel("gold storage", ("gold storage",), "building"),
    SemanticLabel("elixir storage", ("elixir storage",), "building"),
    SemanticLabel("dark elixir storage", ("dark elixir storage",), "building"),
)


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


class SelectionContextDetector:
    """Identify an object from fresh semantic evidence around an action target."""

    def __init__(self, labels: Iterable[SemanticLabel] = SEMANTIC_LABELS) -> None:
        self.labels = tuple(labels)

    def identify(
        self,
        action_name: str,
        target: Optional[Target],
        evidence: Iterable[str],
        village: str,
        confidence: float,
        source: str = "semantic",
    ) -> Optional[SelectionContext]:
        if target is None:
            return None
        if confidence <= 0.0 or target.confidence <= 0.0:
            return None

        corpus = _normalize(" ".join(str(value) for value in evidence if value))
        if not corpus:
            return None

        matches: list[SemanticLabel] = []
        for label in self.labels:
            if any(_normalize(alias) in corpus for alias in label.aliases):
                matches.append(label)

        if not matches:
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

        compatible = [
            item
            for item in matches
            if item.feature == required_feature
            or (
                required_feature in {"builder_laboratory", "builder_wall", "builder_building"}
                and item.feature == required_feature.removeprefix("builder_")
            )
        ]
        if not compatible:
            return None

        selected = compatible[0]
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
            source=source,
            confidence=min(float(confidence), target.confidence),
            features=frozenset(features),
        )
