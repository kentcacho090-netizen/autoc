"""Deterministic tests for AutoC's non-device core logic."""
from __future__ import annotations

import unittest

from accessibility import AccessibilityInspector
from action_gate import SemanticActionGate
from automation_state import Action, SmartAutomationStateMachine, Target
from selection_context import SelectionContextDetector
from strategy import AccountState, SmartPlanner
from vision import ScreenDetector


class AccessibilityTests(unittest.TestCase):
    def test_valid_bounds(self):
        self.assertEqual(
            AccessibilityInspector._parse_bounds("[10,20][110,220]"),
            (10, 20, 110, 220),
        )

    def test_invalid_bounds_are_rejected(self):
        self.assertIsNone(AccessibilityInspector._parse_bounds("[10,20][10,220]"))
        self.assertIsNone(AccessibilityInspector._parse_bounds("not-bounds"))


class VisionTests(unittest.TestCase):
    def test_parse_number_plain(self):
        self.assertEqual(ScreenDetector.parse_number("1,234,567"), 1234567)

    def test_parse_number_suffixes(self):
        self.assertEqual(ScreenDetector.parse_number("1.5M"), 1500000)
        self.assertEqual(ScreenDetector.parse_number("750K"), 750000)
        self.assertEqual(ScreenDetector.parse_number("2B"), 2000000000)

    def test_parse_number_rejects_text(self):
        self.assertIsNone(ScreenDetector.parse_number("gold"))


class SafetyTests(unittest.TestCase):
    def test_missing_target_refuses_action(self):
        machine = SmartAutomationStateMachine(min_target_confidence=0.80)
        decision = type("Decision", (), {"action": "building_upgrade", "reason": "test", "safe": True})()
        action = machine.plan_action(decision, {})
        self.assertFalse(action.safe)
        self.assertIsNone(action.target)

    def test_action_category_can_use_verified_upgrade_button(self):
        machine = SmartAutomationStateMachine(min_target_confidence=0.80)
        decision = type("Decision", (), {"action": "building_upgrade", "reason": "test", "safe": True})()
        target = Target("upgrade", (100, 100), 0.99)
        action = machine.plan_action(decision, {"upgrade": target})
        self.assertTrue(action.safe)
        self.assertEqual(action.target.name, "upgrade")
        self.assertTrue(machine.before_action(action))

    def test_low_confidence_target_refuses_action(self):
        machine = SmartAutomationStateMachine(min_target_confidence=0.80)
        decision = type("Decision", (), {"action": "laboratory", "reason": "test", "safe": True})()
        target = Target("laboratory", (100, 100), 0.79)
        action = machine.plan_action(decision, {"laboratory": target})
        self.assertFalse(action.safe)
        self.assertIsNone(action.target)

    def test_approved_exact_target_can_enter_action_phase(self):
        machine = SmartAutomationStateMachine(min_target_confidence=0.80)
        decision = type("Decision", (), {"action": "laboratory", "reason": "test", "safe": True})()
        target = Target("laboratory", (100, 100), 0.95)
        action = machine.plan_action(decision, {"laboratory": target})
        self.assertTrue(action.safe)
        self.assertIsNotNone(action.target)
        self.assertTrue(machine.before_action(action))

    def test_generic_upgrade_without_object_context_is_refused(self):
        gate = SemanticActionGate(min_context_confidence=0.85)
        action = Action(
            name="building_upgrade",
            target=Target("upgrade", (100, 100), 0.99),
            reason="test",
            safe=True,
        )
        self.assertFalse(gate.authorize(action, action.target, None))


class SelectionContextTests(unittest.TestCase):
    def setUp(self):
        self.detector = SelectionContextDetector()
        self.target = Target("upgrade", (100, 100), 0.96)

    def test_building_label_authorizes_building_upgrade(self):
        context = self.detector.identify(
            "building_upgrade",
            self.target,
            ["Cannon Level 8", "Upgrade"],
            "home",
            0.94,
        )
        self.assertIsNotNone(context)
        self.assertEqual(context.object_type, "building")
        self.assertIn("building", context.features)

    def test_upgrade_label_alone_does_not_identify_building(self):
        context = self.detector.identify(
            "building_upgrade",
            self.target,
            ["Upgrade"],
            "home",
            0.99,
        )
        self.assertIsNone(context)

    def test_laboratory_context_is_specific(self):
        context = self.detector.identify(
            "laboratory",
            self.target,
            ["Laboratory", "Research"],
            "home",
            0.95,
        )
        self.assertIsNotNone(context)
        self.assertEqual(context.object_type, "laboratory")
        self.assertIn("laboratory", context.features)

    def test_builder_laboratory_exposes_required_feature(self):
        context = self.detector.identify(
            "builder_lab",
            self.target,
            ["Laboratory", "Research"],
            "builder_base",
            0.95,
        )
        self.assertIsNotNone(context)
        self.assertIn("builder_laboratory", context.features)

    def test_wrong_object_type_does_not_authorize_hero(self):
        context = self.detector.identify(
            "hero_upgrade",
            self.target,
            ["Cannon", "Upgrade"],
            "home",
            0.95,
        )
        self.assertIsNone(context)


class StrategyTests(unittest.TestCase):
    def test_unknown_observation_does_not_authorize_action(self):
        planner = SmartPlanner(confidence_threshold=0.70)
        decision = planner.choose(AccountState(village="home", confidence=0.20))
        self.assertEqual(decision.action, "observe")
        self.assertFalse(decision.safe)

    def test_pre_th7_missing_dark_elixir_does_not_block_home_strategy(self):
        planner = SmartPlanner(confidence_threshold=0.70)
        state = AccountState(
            village="home",
            gold=500000,
            elixir=500000,
            dark_elixir=None,
            confidence=0.90,
        )
        decision = planner.choose(state)
        self.assertIn(decision.action, {"farm", "observe"})
        self.assertFalse(decision.safe)


if __name__ == "__main__":
    unittest.main()
