# config.py

# --- DEVICE SETTINGS ---
# Run 'adb shell wm size' in Termux to find your resolution
SCREEN_WIDTH = 1080
SCREEN_HEIGHT = 2400

# --- COORDINATES (X, Y) ---
# You must find these by enabling "Pointer Location" in Developer Options
# and tapping the buttons in COC to get the X,Y values.

BTN_COLLECT_ALL = (900, 2100)   # Example: Bottom right area
BTN_ATTACK = (540, 2200)        # Example: Bottom center
BTN_NEXT_OPPONENT = (950, 2150) # Example: 'Next' button in search
BTN_GO = (980, 2150)            # Example: 'Go' button to start attack
BTN_RETURN_HOME = (540, 2300)   # Example: End battle/Return home

# --- TIMING (Seconds) ---
TIME_BETWEEN_ATTACKS = 10
TIME_TO_WAIT_FOR_BATTLE = 90    # Max time to wait for a battle to finish
