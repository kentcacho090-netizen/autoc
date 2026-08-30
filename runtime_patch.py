"""Small runtime wiring layer for AutoC's adaptive Town Hall probe.

The core detector intentionally stays conservative: the probe runs only after a
home-village observation has been established and only once per process unless
it succeeds. This keeps the existing BotService unchanged while connecting the
already-tested TownHallProbe to the live observation pipeline.
"""
from __future__ import annotations

from typing import Any

from townhall import TownHallProbe
from vision import ScreenDetector


_INSTALLED = False
_ORIGINAL_OBSERVE = None


def install_runtime_patches() -> None:
    global _INSTALLED, _ORIGINAL_OBSERVE
    if _INSTALLED:
        return

    _ORIGINAL_OBSERVE = ScreenDetector.observe

    def observe_with_townhall(self: ScreenDetector, image_path=None):
        observation = _ORIGINAL_OBSERVE(self, image_path)
        if observation.town_hall is not None:
            return observation
        if observation.village != "home":
            return observation
        if getattr(self, "_autoc_townhall_attempted", False):
            return observation

        self._autoc_townhall_attempted = True
        try:
            probe = TownHallProbe(self.controller, getattr(self, "_config_path", "detector_config.json"))
            result = probe.probe("autoc_townhall_auto.png")
            if result.level is not None:
                observation.town_hall = result.level
                observation.town_hall_confidence = result.confidence
                observation.diagnostics = (
                    observation.diagnostics
                    + f"; townhall_probe=matched:{result.level}@{result.confidence:.2f}"
                )
            else:
                observation.diagnostics += "; townhall_probe=not_detected"
        except Exception as exc:
            observation.diagnostics += f"; townhall_probe=error:{exc}"
        return observation

    ScreenDetector.observe = observe_with_townhall
    _INSTALLED = True
