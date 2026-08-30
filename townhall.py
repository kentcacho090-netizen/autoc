"""Non-invasive Town Hall observation for AutoC.

Town Hall detection may only report evidence from the current screen. This
module deliberately does not probe guessed board coordinates: a coordinate
without a current vision/accessibility target is never an authorized action.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

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
    tap: Optional[tuple[int, int]] = None
    screenshot: Optional[str] = None
    raw_text: str = ""
    diagnostics: str = ""


class TownHallProbe:
    """Read Town Hall evidence from a fresh screenshot without blind tapping."""

    def __init__(self, controller, config_path="detector_config.json"):
        self.controller = controller
        self.config_path = config_path

    @staticmethod
    def _ocr(image) -> str:
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
    def _parse_level(text: str):
        normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
        for pattern in (
            r"town\s*hall\s*(?:level\s*)?(\d{1,2})",
            r"townhall\s*(?:level\s*)?(\d{1,2})",
            r"\bth\s*(?:level\s*)?(\d{1,2})\b",
        ):
            match = re.search(pattern, normalized)
            if match:
                level = int(match.group(1))
                if 1 <= level <= 20:
                    return level, 0.98
        return None, 0.0

    def probe(self, screenshot_path="autoc_townhall.png") -> TownHallObservation:
        path = self.controller.take_screenshot(screenshot_path)
        if not path or not os.path.exists(path):
            return TownHallObservation(diagnostics="Unable to capture current screenshot")
        if Image is None:
            return TownHallObservation(
                screenshot=path,
                diagnostics="Pillow is unavailable; no Town Hall evidence was evaluated",
            )
        try:
            with Image.open(path) as image:
                raw = self._ocr(image)
        except (OSError, ValueError) as exc:
            return TownHallObservation(screenshot=path, diagnostics=f"Cannot read screenshot: {exc}")

        level, confidence = self._parse_level(raw)
        if level is None:
            return TownHallObservation(
                screenshot=path,
                raw_text=raw,
                diagnostics="No explicit Town Hall level found; no coordinate was tapped",
            )
        return TownHallObservation(
            level=level,
            confidence=confidence,
            screenshot=path,
            raw_text=raw,
            diagnostics="Town Hall level obtained from current screenshot OCR; no blind probe",
        )
