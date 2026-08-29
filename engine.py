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

    def foreground_package(self):
        """Return the best package signal available on the cloud phone."""
        commands = (
            "dumpsys activity activities | grep -E 'mResumedActivity|mFocusedActivity' | tail -n 5",
            "dumpsys window windows | grep -E 'mFocusedApp|mCurrentFocus' | tail -n 5",
        )
        # Prefer resumed/focused app lines, but don't assume the first token is useful.
        for command in commands:
            result = self.run(command)
            if not result:
                continue
            packages = re.findall(r"([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)/", result)
            if packages:
                return packages[0]
        return None

    def package_running(self, package):
        """Check whether Android has a live process for the package."""
        result = self.run(f"pidof {package}")
        if result and re.search(r"\d", result):
            return True
        # Some Android builds don't expose pidof; fall back to dumpsys activity text.
        result = self.run("dumpsys activity processes | grep -F " + package + " | head -n 5")
        return bool(result and package in result)

    def resolve_launcher_activity(self, package):
        """Resolve the package's launcher activity without hard-coding an activity name."""
        result = self.run(
            f"cmd package resolve-activity --brief -a android.intent.action.MAIN "
            f"-c android.intent.category.LAUNCHER {package} | tail -n 1"
        )
        if result and "/" in result and package in result:
            return result.strip()
        return None

    def launch(self, package, wait=5):
        """Launch a package and tolerate floating-window foreground reporting."""
        if not self.package_installed(package):
            print(f"[Android] Package not installed: {package}")
            return False

        activity = self.resolve_launcher_activity(package)
        result = None
        if activity:
            result = self.run(f"am start -n {activity}")
        if result is None:
            result = self.run(
                f"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {package}"
            )
        # monkey is a useful fallback when a cloud-phone launcher rejects am start.
        if result is None:
            result = self.run(f"monkey -p {package} 1")

        time.sleep(max(1, int(wait)))
        current = self.foreground_package()
        running = self.package_running(package)
        active = current == package
        print(f"[Android] Resumed/foreground package: {current or 'unknown'}")
        print(f"[Android] Target process running: {'YES' if running else 'NO'}")
        if not active and not running:
            print(f"[Android] Target did not become active/running: {package}")
            return False
        # A floating Termux window may remain mCurrentFocus even while the game process is active.
        return True

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
