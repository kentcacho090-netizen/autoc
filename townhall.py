"""Adaptive Town Hall detection for the Termux Android controller.

The probe uses vision/OCR-guided taps rather than requiring one permanent
Town Hall coordinate. It tries a bounded set of likely village-board points,
reads the selected-object panel, and stops only when the panel identifies a
Town Hall. The scan is resolution-aware and avoids pressing Back when no
object panel was actually detected.
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
    from PIL import Image, ImageEnhance, ImageOps
except ImportError:
    Image = None
    ImageEnhance = None
    ImageOps = None


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
        self.wait_seconds = max(0.30, float(cfg.get("wait_seconds", 0.65)))
        self.auto_scan = bool(cfg.get("auto_scan", True))
        self.scan_span = max(0.10, min(0.45, float(cfg.get("scan_span", 0.24))))
        self.scan_steps = max(3, min(9, int(cfg.get("scan_steps", 3))))

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
            image = image.convert("L")
            if ImageOps is not None:
                image = ImageOps.autocontrast(image)
            if ImageEnhance is not None:
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
                check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
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

    def _candidate_points(self):
        """Return bounded normalized-board taps, without duplicate points."""
        cx = min(0.82, max(0.18, self.x_norm))
        cy = min(0.82, max(0.18, self.y_norm))
        points = []
        seen = set()

        def add(x, y):
            key = (round(min(0.82, max(0.18, x)), 4), round(min(0.82, max(0.18, y)), 4))
            if key not in seen:
                seen.add(key)
                points.append(key)

        add(cx, cy)
        if not self.auto_scan:
            return points

        radius = self.scan_span / 2.0
        for i in range(1, (self.scan_steps + 1) // 2 + 1):
            delta = radius * i / max(1, (self.scan_steps + 1) // 2)
            for ox, oy in ((-delta, 0), (delta, 0), (0, -delta), (0, delta)):
                add(cx + ox, cy + oy)

        for y in (0.30, 0.45, 0.60, 0.75):
            for x in (0.30, 0.45, 0.60, 0.75):
                add(x, y)
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

        candidates = self._candidate_points()
        attempts = []

        for index, (xn, yn) in enumerate(candidates, start=1):
            x = max(0, min(width - 1, int(width * xn)))
            y = max(0, min(height - 1, int(height * yn)))
            print(f"[TownHall] Smart scan {index}/{len(candidates)} -> {x}, {y}")

            self.controller.tap(x, y)
            time.sleep(self.wait_seconds)
            path = screenshot_path if index == 1 else f"autoc_townhall_scan_{index}.png"
            path = self.controller.take_screenshot(path)
            if not path or not os.path.exists(path):
                attempts.append(f"{x},{y}:screenshot-failed")
                continue

            try:
                with Image.open(path) as image:
                    raw = self._ocr(image)
            except (OSError, ValueError):
                raw = ""
                attempts.append(f"{x},{y}:image-error")

            level, confidence = self._parse_level(raw)
            normalized = re.sub(r"[^a-z0-9]+", " ", raw.lower())
            is_townhall = bool(re.search(r"town\s*hall|townhall", normalized))
            attempts.append(f"{x},{y}:{'townhall' if is_townhall else 'other'}")

            if level is not None or is_townhall:
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

            # Only press Back after OCR has evidence that an object panel is
            # open. A blind Back on the village board could leave the game.
            if self._looks_like_object_panel(raw):
                self._close_panel()

        return TownHallObservation(
            screenshot=screenshot_path,
            diagnostics=(
                f"screen={width}x{height}; smart_scan=yes; matched=no; "
                f"attempts={len(candidates)}; " + "; ".join(attempts[-12:])
            ),
        )
