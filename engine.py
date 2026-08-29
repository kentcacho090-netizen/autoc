"""Reliable Android/ADB control layer for AUTO.

The controller is deliberately small: it owns ADB discovery, shell commands,
taps/swipes, and screenshots. Game logic stays outside this module.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from typing import Optional, Sequence


class ADBError(RuntimeError):
    """Raised when an ADB operation cannot be completed."""


class ADBController:
    def __init__(self, device: Optional[str] = None, adb_path: str = "adb"):
        self.adb_path = adb_path
        self.device = device or os.environ.get("AUTO_ADB_DEVICE")

    def _base(self) -> list[str]:
        cmd = [self.adb_path]
        if self.device:
            cmd += ["-s", self.device]
        return cmd

    def run(self, *args: str, timeout: float = 15.0, check: bool = True) -> str:
        """Run ADB without shell=True and return stdout."""
        cmd = self._base() + [str(a) for a in args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ADBError("adb was not found. Install Android platform-tools.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ADBError(f"ADB timed out: {' '.join(shlex.quote(x) for x in cmd)}") from exc

        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ADBError(f"ADB failed ({result.returncode}): {detail or 'unknown error'}")
        return result.stdout

    def _ensure_device(self) -> str:
        """Select the first ready device when no device was configured."""
        if self.device:
            state = self.run("get-state", check=False).strip()
            if state == "device":
                return self.device
            raise ADBError(f"Configured ADB device '{self.device}' is not ready ({state or 'no response'}).")

        output = self.run("devices", check=True)
        devices = []
        for line in output.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        if not devices:
            raise ADBError("No Android device is connected to ADB.")
        self.device = devices[0]
        return self.device

    def check_connection(self) -> bool:
        try:
            self._ensure_device()
            print(f"[Android] ADB device ready: {self.device}")
            return True
        except ADBError as exc:
            print(f"[Android] {exc}")
            return False

    def tap(self, x: int, y: int, wait: float = 0.35) -> None:
        x, y = int(x), int(y)
        print(f"[Action] Tap ({x}, {y})")
        self.run("shell", "input", "tap", str(x), str(y), timeout=5)
        if wait:
            time.sleep(wait)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300, wait: float = 0.5) -> None:
        print(f"[Action] Swipe ({x1},{y1}) -> ({x2},{y2}) {duration}ms")
        self.run("shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(duration)), timeout=8)
        if wait:
            time.sleep(wait)

    def keyevent(self, key: str, wait: float = 0.25) -> None:
        self.run("shell", "input", "keyevent", str(key), timeout=5)
        if wait:
            time.sleep(wait)

    def launch(self, package: str) -> None:
        """Bring a package to the foreground."""
        self.run("shell", "monkey", "-p", package, "1", timeout=20)
        time.sleep(2)

    def current_package(self) -> Optional[str]:
        out = self.run(
            "shell", "dumpsys", "activity", "activities", timeout=10, check=False
        )
        # Android versions expose mResumedActivity or ResumedActivity.
        for line in out.splitlines():
            if "mResumedActivity" in line or "ResumedActivity" in line:
                parts = line.split()
                for token in parts:
                    if "/" in token and "." in token.split("/")[0]:
                        return token.split("/")[0].strip("}")
        return None

    def take_screenshot(self, filename: str = "autoc_observation.png") -> str:
        """Capture directly through exec-out, avoiding remote pull races."""
        directory = os.path.dirname(os.path.abspath(filename)) or "."
        os.makedirs(directory, exist_ok=True)
        target = os.path.abspath(filename)
        cmd = self._base() + ["exec-out", "screencap", "-p"]
        try:
            with open(target, "wb") as fh:
                result = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, timeout=20)
        except FileNotFoundError as exc:
            raise ADBError("adb was not found. Install Android platform-tools.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ADBError("ADB screenshot timed out.") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise ADBError(f"Screenshot failed: {detail or result.returncode}")
        if not os.path.isfile(target) or os.path.getsize(target) < 100:
            raise ADBError("ADB returned an empty/invalid screenshot.")
        print(f"[System] Screenshot saved as {target}")
        return target
