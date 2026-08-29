"""Verified Android actions: observe immediately before and after every tap."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from ui_targets import UITarget, UITargetDetector


@dataclass
class ActionResult:
    ok: bool
    target: Optional[UITarget] = None
    reason: str = ""
    before: Optional[str] = None
    after: Optional[str] = None


class VerifiedActions:
    def __init__(self, controller, target_detector=None):
        self.controller = controller
        self.targets = target_detector or UITargetDetector()

    def tap_named(self, target_name: str, wait: float = 0.7) -> ActionResult:
        """Tap only a target found in the fresh screenshot.

        This deliberately refuses to accept arbitrary coordinates.  A later
        strategy layer can decide *which* target is appropriate; this class
        only makes the resulting tap observable and reversible.
        """
        before = self.controller.take_screenshot("autoc_action_before.png")
        if not before:
            return ActionResult(False, reason="Could not capture pre-action screen")

        target = self.targets.best(before, target_name)
        if target is None:
            return ActionResult(False, before=before, reason=f"Verified target not visible: {target_name}")

        self.controller.tap(target.x, target.y)
        time.sleep(max(0.2, wait))
        after = self.controller.take_screenshot("autoc_action_after.png")
        if not after:
            return ActionResult(False, target=target, before=before, reason="Post-action screenshot failed")

        return ActionResult(True, target=target, before=before, after=after, reason="Target tapped and post-action screen captured")
