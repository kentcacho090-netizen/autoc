"""Conservative smart strategy for AutoC.

The planner decides *categories*, never raw coordinates.  Perception must
supply a verified target before the action layer is allowed to tap anything.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AccountState:
    village: str = "unknown"
    town_hall: Optional[int] = None
    builder_base_unlocked: bool = False
    builders_free: int = 0
    gold: Optional[int] = None
    elixir: Optional[int] = None
    dark_elixir: Optional[int] = None
    heroes_available: List[str] = field(default_factory=list)
    research_available: bool = False
    upgrade_candidates: List[str] = field(default_factory=list)
    wall_upgrade_available: bool = False
    confidence: float = 0.0


@dataclass
class Decision:
    action: str
    reason: str
    safe: bool = False


class SmartPlanner:
    """Choose the next upgrade category from observed account state.

    Missing optional resources are treated as normal when the feature is not
    unlocked.  The planner never turns an unknown observation into permission
    to tap a guessed coordinate.
    """

    def __init__(self, strategy="balanced", confidence_threshold=0.70):
        self.strategy = strategy
        self.confidence_threshold = confidence_threshold

    def choose(self, state: AccountState) -> Decision:
        if state.confidence < self.confidence_threshold:
            return Decision("observe", "Observation confidence is below the safe threshold")

        if state.village == "home":
            # Hero upgrades become relevant only after heroes exist.  Keep the
            # decision category separate so the action layer can verify the
            # actual hero button before tapping.
            if state.heroes_available:
                return Decision("hero_upgrade", f"Hero available: {state.heroes_available[0]}", True)

            if state.research_available:
                return Decision("laboratory", "Research is available", True)

            if state.builders_free > 0 and state.upgrade_candidates:
                return Decision("building_upgrade", "Builder and upgrade candidate confirmed", True)

            if state.builders_free > 0 and state.wall_upgrade_available:
                return Decision("wall_upgrade", "Builder and wall upgrade confirmed", True)

            return Decision("farm", "No confirmed upgrade is currently actionable", False)

        if state.village == "builder_base":
            if not state.builder_base_unlocked:
                return Decision("observe", "Builder Base is not unlocked")
            if state.research_available:
                return Decision("builder_lab", "Builder Base research is available", True)
            if state.builders_free > 0 and state.upgrade_candidates:
                return Decision("builder_upgrade", "Builder Base upgrade candidate confirmed", True)
            if state.builders_free > 0 and state.wall_upgrade_available:
                return Decision("builder_wall_upgrade", "Builder Base wall upgrade is confirmed", True)
            return Decision("builder_farm", "No confirmed Builder Base upgrade is currently actionable", False)

        return Decision("observe", "Village type is unknown")
