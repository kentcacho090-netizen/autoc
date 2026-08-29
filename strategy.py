"""Conservative, state-driven strategy selection for AutoC."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AccountState:
    village: str = "unknown"
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
    """Choose a next category from observed state.

    The planner is deliberately conservative: it will not invent missing state
    and it will not authorize an action when observation confidence is too low.
    """

    def __init__(self, strategy="balanced", confidence_threshold=0.7):
        self.strategy = strategy
        self.confidence_threshold = confidence_threshold

    def choose(self, state: AccountState) -> Decision:
        if state.confidence < self.confidence_threshold:
            return Decision("observe", "Observation confidence is below the safe threshold")

        if state.village == "home":
            if state.heroes_available:
                return Decision("hero_upgrade", f"Hero available: {state.heroes_available[0]}", True)
            if state.research_available:
                return Decision("laboratory", "Research is available", True)
            if state.builders_free > 0 and state.upgrade_candidates:
                return Decision("building_upgrade", "Builder and upgrade candidate confirmed", True)
            if state.builders_free > 0 and state.wall_upgrade_available:
                return Decision("wall_upgrade", "Builder and wall upgrade confirmed", True)
            return Decision("farm", "No confirmed upgrade is currently actionable", True)

        if state.village == "builder_base":
            if state.research_available:
                return Decision("builder_lab", "Builder Base research is available", True)
            if state.builders_free > 0 and state.upgrade_candidates:
                return Decision("builder_upgrade", "Builder Base upgrade candidate confirmed", True)
            if state.builders_free > 0 and state.wall_upgrade_available:
                return Decision("builder_wall_upgrade", "Builder Base wall upgrade is confirmed", True)
            return Decision("builder_farm", "No confirmed Builder Base upgrade is currently actionable", True)

        return Decision("observe", "Village type is unknown")
