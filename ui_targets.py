"""Verified UI-target detection for AutoC.

Targets are discovered from the current screenshot.  AutoC never taps a
hard-coded coordinate through this module: a target must be visible in the
fresh screenshot and its OCR bounding box must satisfy the confidence/size
checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import shutil
import subprocess
import tempfile
from typing import Iterable, Optional

try:
    from PIL import Image
except ImportError:
    Image = None


@dataclass(frozen=True)
class UITarget:
    name: str
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


TARGET_ALIASES = {
    "town_hall": ("town hall", "townhall"),
    "upgrade": ("upgrade", "upgrading"),
    "collect": ("collect", "collect all"),
    "attack": ("attack", "find a match", "find match"),
    "return_home": ("return home", "return"),
    "builder": ("builder", "builders"),
    "laboratory": ("laboratory", "research"),
}


class UITargetDetector:
    def __init__(self, confidence_threshold: float = 0.55):
        self.confidence_threshold = confidence_threshold

    @staticmethod
    def _ocr_data(image_path: str):
        if Image is None or not shutil.which("tesseract"):
            return []
        temp = None
        try:
            with Image.open(image_path) as im:
                im = im.convert("RGB")
                fd, temp = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                im.save(temp, format="PNG")
            p = subprocess.run(
                ["tesseract", temp, "stdout", "--psm", "11", "tsv"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if p.returncode != 0:
                return []
            rows = []
            for line in p.stdout.splitlines()[1:]:
                cols = line.split("\t")
                if len(cols) < 12:
                    continue
                try:
                    conf = float(cols[10]) / 100.0
                    text = cols[11].strip()
                    x, y, w, h = map(int, cols[6:10])
                except (ValueError, IndexError):
                    continue
                if text and conf >= self.confidence_threshold and w >= 5 and h >= 5:
                    rows.append((text, x, y, w, h, conf))
            return rows
        except (OSError, subprocess.SubprocessError):
            return []
        finally:
            if temp:
                try:
                    os.unlink(temp)
                except OSError:
                    pass

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip()

    def find(self, image_path: str, names: Optional[Iterable[str]] = None):
        wanted = tuple(names or TARGET_ALIASES.keys())
        aliases = {name: TARGET_ALIASES.get(name, (name,)) for name in wanted}
        words = self._ocr_data(image_path)
        targets = []
        for text, x, y, w, h, conf in words:
            normalized = self._norm(text)
            for name, variants in aliases.items():
                if any(v in normalized for v in variants):
                    targets.append(UITarget(name, text, x + w // 2, y + h // 2, w, h, conf))
        return targets

    def best(self, image_path: str, name: str) -> Optional[UITarget]:
        matches = [t for t in self.find(image_path, (name,)) if t.name == name]
        return max(matches, key=lambda t: t.confidence, default=None)
