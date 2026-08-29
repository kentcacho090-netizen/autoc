"""State machine for AutoC's smart automation loop.

The state machine separates perception, decision making, action execution and
verification.  It deliberately refuses to invent a tap when the vision layer
has not supplied a verified target.  This is the core needed for dynamic,
resolution-independent automation rather than hard-coded screen coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class Phase(str, Enum):
    LAUNCH = "launch"
    OBSERVE = "observe"
    PLAN = "plan"
    ACT = "act"
    VERIFY = "verify"
    RECOVER = "recover"
    PAUSED = "paused"


@dataclass
class Target:
    name: str
    center: Tuple[int, int]
    confidence: float
    source: str = "vision"


@dataclass
class Action:
    name: str
    target: Optional[Target] = None
    args: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    safe: bool = False


@dataclass
class CycleState:
    phase: Phase = Phase.OBSERVE
    consecutive_failures: int = 0
    last_action: Optional[str] = None
    last_error: Optional[str] = None


class SmartAutomationStateMachine:
    """Small deterministic controller around the existing planner.

    A decision may only become an executable action when it contains a
    confidence-checked target.  This prevents the old fixed-coordinate failure
    mode where a guessed point could select a wall or another building.
    """

    def __init__(self, min_target_confidence: float = 0.80, max_failures: int = 3):
        self.min_target_confidence = min_target_confidence
        self.max_failures = max_failures
        self.state = CycleState()

    def reset(self):
        self.state = CycleState()

    def plan_action(self, decision: Any, targets: Dict[str, Target]) -> Action:
        action_name = getattr(decision, "action", "observe")
        reason = getattr(decision, "reason", "")
        safe = bool(getattr(decision, "safe", False))

        if action_name in {"observe", "farm", "builder_farm"}:
            return Action(action_name, reason=reason, safe=False)

        target = targets.get(action_name) or targets.get("upgrade")
        if target is None:
            return Action("observe", reason=f"No verified target for {action_name}", safe=False)

        if target.confidence < self.min_target_confidence:
            return Action(
                "observe",
                reason=f"Target confidence {target.confidence:.2f} is below {self.min_target_confidence:.2f}",
                safe=False,
            )

        return Action(action_name, target=target, reason=reason, safe=safe)

    def before_action(self, action: Action) -> bool:
        if not action.safe or action.target is None:
            self.state.phase = Phase.OBSERVE
            return False
        self.state.phase = Phase.ACT
        self.state.last_action = action.name
        return True

    def after_action(self, verified: bool, error: Optional[str] = None):
        if verified:
            self.state.phase = Phase.VERIFY
            self.state.consecutive_failures = 0
            self.state.last_error = None
        else:
            self.state.consecutive_failures += 1
            self.state.last_error = error or "Action was not verified"
            self.state.phase = (
                Phase.PAUSED if self.state.consecutive_failures >= self.max_failures else Phase.RECOVER
            )

    @property
    def paused(self) -> bool:
        return self.state.phase == Phase.PAUSED
