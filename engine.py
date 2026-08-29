"""Android control layer for a rooted cloud-phone Termux environment."""
import os
import shutil
import subprocess
import time


class AndroidController:
    def __init__(self, use_root=True):
        self.use_root = use_root and shutil.which("su") is not None

    def run(self, command):
        """Run an Android shell command locally or through root."""
        if self.use_root:
            args = ["su", "-c", command]
        else:
            args = ["sh", "-c", command]
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"[Android] Command failed: {exc}")
            return None

    def tap(self, x, y):
        print(f"[Action] Tapping at {x}, {y}")
        return self.run(f"input tap {int(x)} {int(y)}")

    def swipe(self, x1, y1, x2, y2, duration=300):
        print(f"[Action] Swiping {x1},{y1} -> {x2},{y2}")
        return self.run(f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration)}")

    def launch(self, package):
        """Launch an Android package using monkey."""
        return self.run(f"monkey -p {package} 1")

    def take_screenshot(self, filename="screen.png"):
        """Save a screenshot in the current Termux directory."""
        target = os.path.abspath(filename)
        remote = "/sdcard/autoc_screen.png"
        if not self.run(f"screencap -p {remote}") is None:
            if self.use_root:
                self.run(f"cp {remote} {target}")
            else:
                # Non-root fallback: Android may expose the file to shell.
                self.run(f"cat {remote} > {target}")
            print(f"[System] Screenshot saved as {target}")
            return target
        return None

    def check_connection(self):
        if self.use_root:
            result = self.run("id")
            connected = bool(result and "uid=" in result)
        else:
            result = self.run("id")
            connected = result is not None
        print("[System] Android control ready." if connected else "[System] Android control unavailable.")
        return connected


# Backwards-compatible name used by older code.
ADBController = AndroidController
