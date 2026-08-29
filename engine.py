# engine.py
import subprocess
import time
import random

class ADBController:
    def __init__(self):
        self.device = "localhost:5555" # Change if using USB/Emulator

    def run_cmd(self, command):
        """Executes an ADB command and returns output."""
        full_cmd = f"adb -s {self.device} {command}"
        try:
            result = subprocess.run(full_cmd.split(), capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Error: {e}")
            return None

    def tap(self, x, y):
        """Simulates a tap."""
        # Add slight randomization to avoid bot detection patterns
        x_rand = x + random.randint(-5, 5)
        y_rand = y + random.randint(-5, 5)
        print(f"[Action] Tapping at {x_rand}, {y_rand}")
        self.run_cmd(f"shell input tap {x_rand} {y_rand}")
        time.sleep(0.5)

    def swipe(self, x1, y1, x2, y2, duration=300):
        """Simulates a swipe."""
        print(f"[Action] Swiping")
        self.run_cmd(f"shell input swipe {x1} {y1} {x2} {y2} {duration}")
        time.sleep(1)

    def take_screenshot(self, filename="screen.png"):
        """Takes a screenshot and pulls it to local storage."""
        self.run_cmd(f"shell screencap -p /sdcard/{filename}")
        self.run_cmd(f"pull /sdcard/{filename} ./{filename}")
        print(f"[System] Screenshot saved as {filename}")

    def check_connection(self):
        """Checks if ADB is connected."""
        result = self.run_cmd("get-state")
        if "device" in result:
            print("[System] ADB Connected!")
            return True
        else:
            print("[System] ADB Disconnected. Please check connection.")
            return False
