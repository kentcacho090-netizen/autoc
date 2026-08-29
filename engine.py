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
        """Return the resumed/focused Android package.

        Some cloud-phone environments report Termux as mCurrentFocus when
        Termux is displayed as a floating window, while mResumedActivity still
        correctly identifies the actual game activity.
        """
        commands = (
            "dumpsys activity activities | grep -E 'mResumedActivity|mFocusedActivity' | tail -n 3",
            "dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp' | tail -n 3",
        )
        for command in commands:
            result = self.run(command)
            if not result:
                continue
            # Prefer a known package-looking token containing an Android activity.
            for line in result.splitlines():
                for token in line.replace("{", " ").replace("}", " ").split():
                    if "/" in token and token.count("/") >= 1:
                        candidate = token.split("/")[0].strip()
                        if "." in candidate and not candidate.startswith(("m", "u0_")):
                            return candidate
        return None

    def launch(self, package, wait=5):
        """Launch a package and report whether it becomes the resumed app."""
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
        print(f"[Android] Resumed/foreground package: {current or 'unknown'}")
        if not ok:
            print(f"[Android] Target did not become active: {package}")
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
