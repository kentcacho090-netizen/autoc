"""Android control layer for a rooted cloud-phone Termux environment."""
import os
import re
import shutil
import subprocess
import time


class AndroidController:
    def __init__(self, use_root=True):
        self.use_root = use_root and shutil.which("su") is not None

    def run(self, command):
        """Run an Android shell command locally or through root."""
        args = ["su", "-c", command] if self.use_root else ["sh", "-c", command]
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

    def package_installed(self, package):
        result = self.run(f"pm path {package}")
        return bool(result and result.startswith("package:"))

    @staticmethod
    def _extract_package(text):
        if not text:
            return None
        # Handles package/.Activity and package/com.example.Activity forms.
        match = re.search(r"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/", text)
        return match.group(1) if match else None

    def foreground_package(self):
        """Return the best foreground/resumed package on Android variants.

        Some cloud-phone builds keep a floating Termux window focused while the
        game remains the resumed activity. Prefer mResumedActivity/mFocusedApp,
        then fall back to window focus.
        """
        commands = [
            "dumpsys activity activities | grep -E 'mResumedActivity|mFocusedActivity' | tail -n 3",
            "dumpsys window windows | grep -E 'mFocusedApp|mCurrentFocus' | tail -n 3",
        ]
        for command in commands:
            result = self.run(command)
            package = self._extract_package(result)
            if package:
                return package
        return None

    def launch(self, package, wait=5):
        """Launch a package and verify its resumed/foreground package."""
        if not self.package_installed(package):
            print(f"[Android] Package not installed: {package}")
            return False

        result = self.run(
            f"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {package}"
        )
        if result is None:
            result = self.run(f"monkey -p {package} 1")
        time.sleep(max(1, int(wait)))
        current = self.foreground_package()
        ok = current == package
        print(f"[Android] Foreground/resumed package: {current or 'unknown'}")
        if not ok:
            print(f"[Android] Target did not become foreground/resumed: {package}")
        return ok

    def take_screenshot(self, filename="screen.png"):
        """Save a screenshot in the current Termux directory."""
        target = os.path.abspath(filename)
        remote = "/sdcard/autoc_screen.png"
        if self.run(f"screencap -p {remote}") is not None:
            if self.use_root:
                self.run(f"cp {remote} {target}")
            else:
                self.run(f"cat {remote} > {target}")
            print(f"[System] Screenshot saved as {target}")
            return target
        return None

    def check_connection(self):
        result = self.run("id")
        connected = bool(result and "uid=" in result)
        print("[System] Android control ready." if connected else "[System] Android control unavailable.")
        return connected


ADBController = AndroidController
