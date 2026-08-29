"""AUTO runtime configuration."""

# --- DEVICE / APP ---
# Leave empty to auto-select the first connected ADB device.
ADB_DEVICE = ""
TARGET_PACKAGE = "com.supercell.clashofclans"

# Your game viewport is 1280x720 landscape.
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# --- DETECTOR ---
DETECTOR_CONFIG = "detector_config.json"
SCREENSHOT_FILE = "autoc_observation.png"
OBSERVE_INTERVAL = 5.0

# These are intentionally NOT used by the current main loop. Do not put
# guessed coordinates here and expect the bot to act on them. Action
# coordinates must come from a positively detected UI state first.
