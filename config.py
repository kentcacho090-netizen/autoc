"""Compatibility configuration for AutoC.

Runtime settings live in ``settings.json`` and ``detector_config.json``.
The Android controller and vision layer discover the current screen instead
of relying on fixed device coordinates.
"""

TIME_BETWEEN_CYCLES = 10
TIME_TO_WAIT_FOR_BATTLE = 90
TARGET_PACKAGE = "com.supercell.clashofclans"
