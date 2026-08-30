"""Verified Android actions: observe, gate, act, then verify semantic change."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from action_verification import PostActionVerifier
from ui_targets import UITarget, UITargetDetector


@dataclass
class ActionResult:
    ok: bool
    target: Optional[UITarget] = None
    reason: str = ""
    before: Optional[str] = None
    after: Optional[str] = None


class VerifiedActions:
    def __init__(self, controller, target_detector=None, verifier=None):
        self.controller = controller
        self.targets = target_detector or UITargetDetector()
        self.verifier = verifier or PostActionVerifier(self.targets.best)

    def tap_named(self, target_name: str, wait: float = 0.7) -> ActionResult:
        """Tap only a fresh target and require semantic post-action change."""
        before = self.controller.take_screenshot("autoc_action_before.png")
        if not before:
            return ActionResult(False, reason="Could not capture pre-action screen")

        target = self.targets.best(before, target_name)
        if target is None:
            return ActionResult(
                False,
                before=before,
                reason=f"Verified target not visible: {target_name}",
            )

        tap_result = self.controller.tap(target.x, target.y)
        if tap_result is None:
            return ActionResult(
                False,
                target=target,
                before=before,
                reason="Android tap command failed",
            )

        time.sleep(max(0.2, wait))
        after = self.controller.take_screenshot("autoc_action_after.png")
        if not after:
            return ActionResult(
                False,
                target=target,
                before=before,
                reason="Post-action screenshot failed",
            )

        verification = self.verifier.verify(target, after)
        if not verification.verified:
            return ActionResult(
                False,
                target=target,
                before=before,
                after=after,
                reason=verification.reason,
            )

        return ActionResult(
            True,
            target=target,
            before=before,
            after=after,
            reason=verification.reason,
        )
