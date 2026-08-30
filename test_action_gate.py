"""Tests for AutoC semantic action authorization."""
from __future__ import annotations

import unittest

from action_gate import SelectionContext, SemanticActionGate
from automation_state import Action, Target


class SemanticActionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = SemanticActionGate(0.85)
        self.target = Target("upgrade", (400, 300), 0.95, "accessibility")

    def context(self, object_type: str | None, confidence: float = 0.95, features=()):
        return SelectionContext(
            object_type=object_type,
            object_name=None,
            village="home",
            source="accessibility",
            confidence=confidence,
            features=frozenset(features),
        )

    def test_generic_upgrade_label_is_not_enough(self) -> None:
        action = Action("building_upgrade", target=self.target, safe=True)
        self.assertFalse(self.gate.authorize(action, self.target, self.context(None)))

    def test_building_upgrade_requires_building_context(self) -> None:
        action = Action("building_upgrade", target=self.target, safe=True)
        self.assertTrue(self.gate.authorize(action, self.target, self.context("building")))

    def test_wrong_context_is_rejected(self) -> None:
        action = Action("hero_upgrade", target=self.target, safe=True)
        self.assertFalse(self.gate.authorize(action, self.target, self.context("building")))

    def test_low_confidence_is_rejected(self) -> None:
        action = Action("building_upgrade", target=self.target, safe=True)
        self.assertFalse(self.gate.authorize(action, self.target, self.context("building", 0.80)))

    def test_unknown_action_is_rejected(self) -> None:
        action = Action("arbitrary_action", target=self.target, safe=True)
        self.assertFalse(self.gate.authorize(action, self.target, self.context("building")))

    def test_builder_upgrade_uses_builder_specific_context(self) -> None:
        action = Action("builder_upgrade", target=self.target, safe=True)
        self.assertFalse(self.gate.authorize(action, self.target, self.context("building")))
        self.assertTrue(
            self.gate.authorize(
                action,
                self.target,
                self.context("builder_building"),
            )
        )


if __name__ == "__main__":
    unittest.main()
