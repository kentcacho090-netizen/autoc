"""Post-action verification using fresh semantic target evidence.

The verifier never assumes that a successful Android command means that the
intended game action happened. It compares the target detected before the tap
with fresh target evidence after the tap. For action-gated upgrades, the
expected result is that the actionable control disappears or materially
changes at the same screen location.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ui_targets import UITarget


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    reason: str
    remaining: Optional[UITarget] = None


def _iou(first: UITarget, second: UITarget) -> float:
    left = max(first.x - first.width // 2, second.x - second.width // 2)
    top = max(first.y - first.height // 2, second.y - second.height // 2)
    right = min(first.x + first.width // 2, second.x + second.width // 2)
    bottom = min(first.y + first.height // 2, second.y + second.height // 2)
    intersection = max(0, right - left) * max(0, bottom - top)
    first_area = max(1, first.width * first.height)
    second_area = max(1, second.width * second.height)
    union = first_area + second_area - intersection
    return intersection / union


class PostActionVerifier:
    """Verify that a previously detected UI target changed after an action."""

    def __init__(
        self,
        target_finder: Callable[[str, str], Optional[UITarget]],
        min_iou: float = 0.35,
    ) -> None:
        self.target_finder = target_finder
        self.min_iou = float(min_iou)

    def verify(self, before: UITarget, after_image: str) -> VerificationResult:
        if not after_image:
            return VerificationResult(False, "Missing post-action screenshot")

        remaining = self.target_finder(after_image, before.name)
        if remaining is None:
            return VerificationResult(True, "Target disappeared after action")

        overlap = _iou(before, remaining)
        if overlap < self.min_iou:
            return VerificationResult(True, "Original target no longer occupies its previous region", remaining)

        text_changed = before.text.strip().lower() != remaining.text.strip().lower()
        geometry_changed = (
            before.width != remaining.width
            or before.height != remaining.height
        )
        confidence_changed = abs(before.confidence - remaining.confidence) >= 0.15
        if text_changed or geometry_changed or confidence_changed:
            return VerificationResult(True, "Target evidence materially changed", remaining)

        return VerificationResult(False, "Target remains materially unchanged after action", remaining)
