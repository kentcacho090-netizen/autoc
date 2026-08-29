"""Adaptive Town Hall detection for the Termux Android controller.

The probe uses a vision/OCR-guided tap search rather than requiring a user to
calibrate one permanent Town Hall coordinate. It tries a small set of likely
village-board points, reads the selected-object panel, and stops only when the
panel identifies a Town Hall. This also makes the probe resilient to camera
panning, zoom changes, and screen rotation/resolution differences.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from PIL import Image, ImageOps, ImageEnhance
except ImportError:
    Image = None


@dataclass
class TownHallObservation:
    level: Optional[int] = None
    confidence: float = 0.0
    tap: Tuple[int, int] = (0, 0)
    screenshot: Optional[str] = None
    raw_text: str = ""
    diagnostics: str = ""


class TownHallProbe:
    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config = self._load_config(config_path)
        cfg = self.config.get("townhall", {})
        self.x_norm = float(cfg.get("x", 0.50))
        self.y_norm = float(cfg.get("y", 0.47))
        self.wait_seconds = float(cfg.get("wait_seconds", 0.65))
        self.auto_scan = bool(cfg.get("auto_scan", True))
        self.scan_span = float(cfg.get("scan_span", 0.30))
        self.scan_steps = max(3, int(cfg.get("scan_steps", 5)))

    @staticmethod
    def _load_config(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _ocr(image):
        if Image is None or not shutil.which("tesseract"):
            return ""
        temp = None
        try:
            # The selected-object panel is normally large, but its orientation
            # varies with the Android display. OCR the full frame so we do not
            # depend on one hard-coded panel rectangle.
            image = image.convert("L")
            image = ImageOps.autocontrast(image)
            image = ImageEnhance.Contrast(image).enhance(1.8)
            image = image.resize((image.width * 2, image.height * 2))
            fd, temp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            image.save(temp, format="PNG")
            result = subprocess.run(
                [
                    "tesseract", temp, "stdout", "--psm", "11",
                    "-c", "load_system_dawg=0",
                    "-c", "load_freq_dawg=0",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
        finally:
            if temp:
                try:
                    os.unlink(temp)
                except OSError:
                    pass

    @staticmethod
    def _parse_level(text):
        if not text:
            return None, 0.0
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
        patterns = (
            r"town\s*hall\s*(?:level\s*)?(\d{1,2})",
            r"townhall\s*(?:level\s*)?(\d{1,2})",
            r"th\s*(?:level\s*)?(\d{1,2})",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                level = int(match.group(1))
                if 1 <= level <= 20:
                    return level, 0.98

        # Some game panels show just "Town Hall" and omit the level from the
        # OCR crop. The account's level can still be inferred safely from the
        # selected-object label only if a nearby standalone number exists.
        if re.search(r"town\s*hall|townhall", normalized):
            nearby = re.findall(r"\b(\d{1,2})\b", normalized)
            for token in nearby:
                level = int(token)
                if 1 <= level <= 20:
                    return level, 0.90
            return None, 0.70
        return None, 0.0

    @staticmethod
    def _looks_like_object_panel(text):
        if not text:
            return False
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
        markers = (
            "info", "upgrade", "select", "wall", "cannon", "builder",
            "town hall", "townhall", "army camp", "barracks", "storage",
        )
        return any(marker in normalized for marker in markers)

    def _candidate_points(self, width, height):
        """Return normalized-board taps from most likely to least likely."""
        cx, cy = self.x_norm, self.y_norm
        points = [(cx, cy)]
        if not self.auto_scan:
            return points

        span = max(0.10, min(0.45, self.scan_span))
        steps = self.scan_steps
        # Start near the configured point and expand outward. This is much
        # faster than scanning the entire screen and avoids HUD controls.
        offsets = [0.0]
        for i in range(1, (steps // 2) + 1):
            offsets.extend([-span * i / (steps // 2 + 1), span * i / (steps // 2 + 1)])

        seen = set()
        for oy in offsets:
            for ox in offsets:
                x = min(0.82, max(0.18, cx + ox))
                y = min(0.82, max(0.18, cy + oy))
                key = (round(x, 4), round(y, 4))
                if key not in seen:
                    seen.add(key)
                    points.append(key)

        # If the configured point is stale because the camera moved, include
        # a coarse board-wide fallback. HUD/resource areas are deliberately
        # excluded.
        for y in (0.25, 0.40, 0.55, 0.70):
            for x in (0.25, 0.40, 0.55, 0.70):
                key = (x, y)
                if key not in seen:
                    seen.add(key)
                    points.append(key)
        return points

    def _close_panel(self):
        self.controller.run("input keyevent 4")
        time.sleep(0.20)

    def probe(self, screenshot_path="autoc_townhall.png"):
        before = self.controller.take_screenshot("autoc_townhall_before.png")
        if not before or Image is None:
            return TownHallObservation(diagnostics="Unable to capture pre-tap screenshot or Pillow is missing")

        try:
            with Image.open(before) as image:
                width, height = image.size
        except (OSError, ValueError) as exc:
            return TownHallObservation(diagnostics=f"Cannot read pre-tap screenshot: {exc}")

        candidates = self._candidate_points(width, height)
        attempts = []

        for index, (xn, yn) in enumerate(candidates, start=1):
            x = max(0, min(width - 1, int(width * xn)))
            y = max(0, min(height - 1, int(height * yn)))
            print(f"[TownHall] Smart scan {index}/{len(candidates)} -> {x}, {y}")

            self.controller.tap(x, y)
            time.sleep(max(0.30, self.wait_seconds))
            path = self.controller.take_screenshot(
                screenshot_path if index == 1 else f"autoc_townhall_scan_{index}.png"
            )
            if not path or not os.path.exists(path):
                self._close_panel()
                attempts.append(f"{x},{y}:screenshot-failed")
                continue

            try:
                with Image.open(path) as image:
                    raw = self._ocr(image)
            except (OSError, ValueError) as exc:
                raw = ""
                attempts.append(f"{x},{y}:image-error")

            level, confidence = self._parse_level(raw)
            normalized = re.sub(r"[^a-z0-9]+", " ", raw.lower())
            attempts.append(f"{x},{y}:{'townhall' if ('town hall' in normalized or 'townhall' in normalized) else 'other'}")

            if level is not None or re.search(r"town\s*hall|townhall", normalized):
                self._close_panel()
                return TownHallObservation(
                    level=level,
                    confidence=confidence,
                    tap=(x, y),
                    screenshot=path,
                    raw_text=raw,
                    diagnostics=(
                        f"screen={width}x{height}; smart_scan=yes; attempts={index}; "
                        f"matched={x},{y}; orientation-adaptive"
                    ),
                )

            # If another selectable object was opened, close it before the next
            # tap. If no panel appeared, Back is harmless and keeps the scan
            # state clean.
            if self._looks_like_object_panel(raw):
                self._close_panel()
            else:
                self._close_panel()

        return TownHallObservation(
            screenshot=screenshot_path,
            diagnostics=(
                f"screen={width}x{height}; smart_scan=yes; matched=no; "
                f"attempts={len(candidates)}; " + "; ".join(attempts[-12:])
            ),
        )
