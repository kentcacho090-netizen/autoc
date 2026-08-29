"""Town Hall probe for the rooted Termux Android controller.

The probe intentionally does not guess a Town Hall level from resource OCR.
It taps the configured Town Hall position, captures the information panel,
reads the Town Hall level, and then closes the panel.
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
        self.wait_seconds = float(cfg.get("wait_seconds", 1.0))
        self.panel = cfg.get("panel", [0.20, 0.05, 0.60, 0.70])

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
            # Upscale and increase contrast so the white panel text is easier
            # for native Termux Tesseract to read.
            image = image.convert("L")
            image = ImageOps.autocontrast(image)
            image = ImageEnhance.Contrast(image).enhance(1.8)
            image = image.resize((image.width * 3, image.height * 3))
            fd, temp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            image.save(temp, format="PNG")
            result = subprocess.run(
                [
                    "tesseract", temp, "stdout", "--psm", "6",
                    "-c", "load_system_dawg=0",
                    "-c", "load_freq_dawg=0",
                ],
                capture_output=True,
                text=True,
                timeout=10,
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
            r"\bth\s*(?:level\s*)?(\d{1,2})\b",
        )
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                level = int(match.group(1))
                if 1 <= level <= 20:
                    return level, 0.95
        # Do not accept an arbitrary cost/time number as the TH level.
        return None, 0.0

    def _panel_crop(self, image):
        x, y, w, h = [float(v) for v in self.panel]
        return image.crop((
            max(0, int(x * image.width)),
            max(0, int(y * image.height)),
            min(image.width, int((x + w) * image.width)),
            min(image.height, int((y + h) * image.height)),
        ))

    def probe(self, screenshot_path="autoc_townhall.png"):
        # Capture first so we know the current display dimensions.
        before = self.controller.take_screenshot("autoc_townhall_before.png")
        if not before or Image is None:
            return TownHallObservation(diagnostics="Unable to capture pre-tap screenshot or Pillow is missing")

        try:
            with Image.open(before) as image:
                width, height = image.size
        except (OSError, ValueError) as exc:
            return TownHallObservation(diagnostics=f"Cannot read pre-tap screenshot: {exc}")

        x = max(0, min(width - 1, int(width * self.x_norm)))
        y = max(0, min(height - 1, int(height * self.y_norm)))
        print(f"[TownHall] Tapping configured Town Hall point: {x}, {y}")
        self.controller.tap(x, y)
        time.sleep(max(0.3, self.wait_seconds))

        path = self.controller.take_screenshot(screenshot_path)
        if not path or not os.path.exists(path):
            self.controller.run("input keyevent 4")
            return TownHallObservation(tap=(x, y), diagnostics="Town Hall panel screenshot failed")

        try:
            with Image.open(path) as image:
                panel = self._panel_crop(image)
                raw = self._ocr(panel)
        except (OSError, ValueError) as exc:
            self.controller.run("input keyevent 4")
            return TownHallObservation(tap=(x, y), screenshot=path, diagnostics=f"Panel OCR image error: {exc}")

        level, confidence = self._parse_level(raw)
        # Always close the information panel before returning control to the bot.
        self.controller.run("input keyevent 4")
        time.sleep(0.3)

        diagnostics = (
            f"screen={width}x{height}; tap={x},{y}; "
            f"panel={self.panel}; label_match={'yes' if level is not None else 'no'}"
        )
        return TownHallObservation(
            level=level,
            confidence=confidence,
            tap=(x, y),
            screenshot=path,
            raw_text=raw,
            diagnostics=diagnostics,
        )
