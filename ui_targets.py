"""Verified dynamic UI-target detection for AutoC.

AutoC combines Android accessibility hierarchy data with screenshot OCR.
Accessibility supplies semantic bounds when Android exposes them; OCR covers
game-rendered text that is not present in the accessibility tree.  Neither
channel is allowed to create an executable tap by itself: callers still pass
the resulting target through the verified action gate.
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

try:
    from accessibility import AccessibilityInspector
except ImportError:
    AccessibilityInspector = None


@dataclass(frozen=True)
class UITarget:
    name: str
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float
    source: str = "ocr"

    @property
    def center(self) -> tuple[int, int]:
        return self.x, self.y


TARGET_ALIASES = {
    "town_hall": ("town hall", "townhall"),
    "upgrade": ("upgrade", "upgrading"),
    "collect": ("collect", "collect all"),
    "attack": ("attack", "find a match", "find match"),
    "return_home": ("return home", "return"),
    "builder": ("builder", "builders"),
    "laboratory": ("laboratory", "research"),
    "hero_upgrade": ("upgrade", "hero"),
    "building_upgrade": ("upgrade",),
    "wall_upgrade": ("upgrade", "wall"),
    "builder_lab": ("upgrade", "research"),
    "builder_upgrade": ("upgrade",),
    "builder_wall_upgrade": ("upgrade", "wall"),
}


class UITargetDetector:
    def __init__(self, confidence_threshold: float = 0.55, accessibility=None):
        self.confidence_threshold = confidence_threshold
        if accessibility is not None:
            self.accessibility = accessibility
        elif AccessibilityInspector is not None:
            self.accessibility = AccessibilityInspector()
        else:
            self.accessibility = None

    def _ocr_data(self, image_path: str):
        """Return OCR word boxes from an image."""
        if Image is None or not shutil.which("tesseract"):
            return []
        temp = None
        try:
            with Image.open(image_path) as im:
                im = im.convert("RGB")
                fd, temp = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                im.save(temp, format="PNG")

            result = subprocess.run(
                ["tesseract", temp, "stdout", "--psm", "11", "tsv"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return []

            rows = []
            for line in result.stdout.splitlines()[1:]:
                cols = line.split("\t")
                if len(cols) < 12:
                    continue
                try:
                    confidence = float(cols[10]) / 100.0
                    text = cols[11].strip()
                    x, y, width, height = map(int, cols[6:10])
                except (ValueError, IndexError):
                    continue
                if text and confidence >= self.confidence_threshold and width >= 5 and height >= 5:
                    rows.append((text, x, y, width, height, confidence))
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

    @staticmethod
    def _contains_variant(normalized: str, variant: str) -> bool:
        normalized_variant = re.sub(r"[^a-z0-9 ]+", " ", variant.lower()).strip()
        if not normalized_variant:
            return False
        return normalized_variant in normalized

    def _accessibility_targets(self, names: tuple[str, ...]) -> list[UITarget]:
        if self.accessibility is None:
            return []
        try:
            nodes = self.accessibility.find(
                variant for name in names for variant in TARGET_ALIASES.get(name, (name,))
            )
        except Exception:
            return []

        targets: list[UITarget] = []
        for node in nodes:
            searchable = node.searchable_text
            normalized = self._norm(searchable)
            for name in names:
                variants = TARGET_ALIASES.get(name, (name,))
                if any(self._contains_variant(normalized, variant) for variant in variants):
                    left, top, right, bottom = node.bounds
                    width = right - left
                    height = bottom - top
                    confidence = 0.97 if node.clickable else 0.90
                    targets.append(
                        UITarget(
                            name=name,
                            text=searchable,
                            x=(left + right) // 2,
                            y=(top + bottom) // 2,
                            width=width,
                            height=height,
                            confidence=confidence,
                            source="accessibility",
                        )
                    )
                    break
        return targets

    def find(self, image_path: str, names: Optional[Iterable[str]] = None):
        wanted = tuple(names or TARGET_ALIASES.keys())
        targets = self._accessibility_targets(wanted)
        words = self._ocr_data(image_path)
        for text, x, y, width, height, confidence in words:
            normalized = self._norm(text)
            for name in wanted:
                variants = TARGET_ALIASES.get(name, (name,))
                if any(self._contains_variant(normalized, variant) for variant in variants):
                    targets.append(
                        UITarget(
                            name=name,
                            text=text,
                            x=x + width // 2,
                            y=y + height // 2,
                            width=width,
                            height=height,
                            confidence=confidence,
                            source="ocr",
                        )
                    )
        return self._deduplicate(targets)

    @staticmethod
    def _deduplicate(targets: list[UITarget]) -> list[UITarget]:
        selected: dict[tuple[str, int, int], UITarget] = {}
        for target in targets:
            key = (target.name, target.x // 8, target.y // 8)
            previous = selected.get(key)
            if previous is None or target.confidence > previous.confidence:
                selected[key] = target
        return sorted(selected.values(), key=lambda target: target.confidence, reverse=True)

    def best(self, image_path: str, name: str) -> Optional[UITarget]:
        matches = [target for target in self.find(image_path, (name,)) if target.name == name]
        return max(matches, key=lambda target: target.confidence, default=None)
