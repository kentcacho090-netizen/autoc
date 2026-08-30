"""Semantic action authorization for AutoC.

A visible ``Upgrade`` label is not enough to authorize an upgrade.  The gate
requires fresh evidence about the selected object or an explicitly identified
context before an action can reach the input layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

from automation_state import Action, Target


@dataclass(frozen=True)
class SelectionContext:
    """Fresh semantic context describing the object currently selected."""

    object_type: Optional[str]
    object_name: Optional[str]
    village: str
    source: str
    confidence: float
    features: FrozenSet[str] = frozenset()

    @property
    def identified(self) -> bool:
        return bool(self.object_type or self.object_name)


ACTION_REQUIREMENTS = {
    "hero_upgrade": frozenset({"hero"}),
    "laboratory": frozenset({"laboratory"}),
    "building_upgrade": frozenset({"building"}),
    "wall_upgrade": frozenset({"wall"}),
    "builder_lab": frozenset({"builder_laboratory"}),
    "builder_upgrade": frozenset({"builder_building"}),
    "builder_wall_upgrade": frozenset({"builder_wall"}),
}


def _context_features(context: SelectionContext) -> FrozenSet[str]:
    values = set(context.features)
    for value in (context.object_type, context.object_name):
        if value:
            values.add(value.strip().lower().replace(" ", "_"))
    return frozenset(values)


class SemanticActionGate:
    """Reject actions whose semantic target has not been independently identified."""

    def __init__(self, min_context_confidence: float = 0.85) -> None:
        self.min_context_confidence = float(min_context_confidence)

    def authorize(
        self,
        action: Action,
        target: Optional[Target],
        context: Optional[SelectionContext],
    ) -> bool:
        if not action.safe or target is None or context is None:
            return False
        if target.confidence < self.min_context_confidence:
            return False
        if context.confidence < self.min_context_confidence:
            return False
        if not context.identified:
            return False

        required = ACTION_REQUIREMENTS.get(action.name)
        if required is None:
            return False

        features = _context_features(context)
        return bool(required & features)
