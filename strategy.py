"""Decision layer for AutoC.

This module deliberately separates strategy from Android input. The detector/state
provider can be upgraded later without rewriting the UI or controller.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class AccountState:
    village: str = "home"
    builders_free: int = 0
    gold: int = 0
    elixir: int = 0
    dark_elixir: int = 0
    heroes_available: List[str] = field(default_factory=list)
    research_available: bool = False
    upgrade_candidates: List[str] = field(default_factory=list)
    wall_upgrade_available: bool = False


@dataclass
class Decision:
    action: str
    reason: str


class SmartPlanner:
    """Chooses a sensible next category from observed state.

    Actual screen/state detection is intentionally injected later. Until then,
    the planner never invents a game state or blindly performs an upgrade.
    """

    def __init__(self, strategy="balanced"):
        self.strategy = strategy

    def choose(self, state: AccountState) -> Decision:
        if state.village == "home":
            if state.heroes_available:
                return Decision("hero_upgrade", f"Hero available: {state.heroes_available[0]}")
            if state.research_available:
                return Decision("laboratory", "Research is available")
            if state.upgrade_candidates and state.builders_free > 0:
                return Decision("building_upgrade", "Builder available and an upgrade candidate was detected")
            if state.wall_upgrade_available and state.builders_free > 0:
                return Decision("wall_upgrade", "Wall upgrade is available and resources can be spent")
            return Decision("farm", "No safe upgrade action is currently confirmed")

        if state.village == "builder_base":
            if state.research_available:
                return Decision("builder_lab", "Builder Base research is available")
            if state.upgrade_candidates and state.builders_free > 0:
                return Decision("builder_upgrade", "Builder Base upgrade candidate detected")
            if state.wall_upgrade_available and state.builders_free > 0:
                return Decision("builder_wall_upgrade", "Builder Base wall upgrade is available")
            return Decision("builder_farm", "No safe Builder Base upgrade action is currently confirmed")

        return Decision("idle", "Unknown village state")
