"""Verified dynamic UI-target detection for AutoC.

AutoC combines Android accessibility hierarchy data with screenshot OCR.
Accessibility supplies semantic bounds when Android exposes them; OCR covers
game-rendered text that is not present in the accessibility tree. OCR words
are also grouped into nearby text runs so multi-word controls such as
"Return Home" and "Town Hall" can be detected without fixed coordinates.
Neither channel is allowed to create an executable tap by itself: callers
still pass the resulting target through the verified action gate.
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

TARGET_REQUIRE_ALL = {
    "hero_upgrade": True,
    "wall_upgrade": True,
    "builder_lab": False,
    "builder_wall_upgrade": True,
}


class UITargetDetector:
    def __init__(self, confidence_threshold: float = 0.55, accessibility=None):
        self.confidence_threshold = float(confidence_threshold)
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

    @classmethod
    def _contains_variant(cls, normalized: str, variant: str) -> bool:
        normalized_variant = cls._norm(variant)
        if not normalized_variant:
            return False
        return normalized_variant in normalized

    @classmethod
    def _matches_name(cls, normalized: str, name: str) -> bool:
        variants = TARGET_ALIASES.get(name, (name,))
        if TARGET_REQUIRE_ALL.get(name, False):
            return all(cls._contains_variant(normalized, variant) for variant in variants)
        return any(cls._contains_variant(normalized, variant) for variant in variants)

    @staticmethod
    def _vertical_overlap_ratio(first, second) -> float:
        first_top = first[2]
        first_bottom = first[2] + first[4]
        second_top = second[2]
        second_bottom = second[2] + second[4]
        overlap = max(0, min(first_bottom, second_bottom) - max(first_top, second_top))
        minimum_height = max(1, min(first[4], second[4]))
        return overlap / minimum_height

    @classmethod
    def _can_join_words(cls, first, second) -> bool:
        if cls._vertical_overlap_ratio(first, second) < 0.50:
            return False
        first_right = first[1] + first[3]
        second_left = second[1]
        gap = second_left - first_right
        maximum_gap = max(20, int(min(first[4], second[4]) * 1.5))
        return 0 <= gap <= maximum_gap

    @classmethod
    def _group_ocr_words(cls, words):
        """Join adjacent OCR words on the same visual text line."""
        if not words:
            return []

        ordered = sorted(words, key=lambda row: (row[2], row[1]))
        groups = []
        current = None
        for word in ordered:
            if current is None:
                current = [word]
                continue
            if cls._can_join_words(current[-1], word):
                current.append(word)
            else:
                groups.append(cls._merge_word_group(current))
                current = [word]
        if current:
            groups.append(cls._merge_word_group(current))
        return groups

    @staticmethod
    def _merge_word_group(group):
        text = " ".join(word[0] for word in group)
        left = min(word[1] for word in group)
        top = min(word[2] for word in group)
        right = max(word[1] + word[3] for word in group)
        bottom = max(word[2] + word[4] for word in group)
        confidence = min(word[5] for word in group)
        return text, left, top, right - left, bottom - top, confidence

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
                if self._matches_name(normalized, name):
                    left, top, right, bottom = node.bounds
                    targets.append(
                        UITarget(
                            name=name,
                            text=searchable,
                            x=(left + right) // 2,
                            y=(top + bottom) // 2,
                            width=right - left,
                            height=bottom - top,
                            confidence=0.97 if node.clickable else 0.90,
                            source="accessibility",
                        )
                    )
                    break
        return targets

    def _ocr_targets(self, image_path: str, names: tuple[str, ...]) -> list[UITarget]:
        words = self._ocr_data(image_path)
        candidates = list(words)
        candidates.extend(grouped for grouped in self._group_ocr_words(words) if grouped not in candidates)

        targets: list[UITarget] = []
        for text, x, y, width, height, confidence in candidates:
            normalized = self._norm(text)
            for name in names:
                if not self._matches_name(normalized, name):
                    continue
                matched_variants = [
                    variant
                    for variant in TARGET_ALIASES.get(name, (name,))
                    if self._contains_variant(normalized, variant)
                ]
                specificity = max((len(self._norm(variant)) for variant in matched_variants), default=1)
                adjusted_confidence = min(1.0, confidence + min(0.08, specificity / 200.0))
                targets.append(
                    UITarget(
                        name=name,
                        text=text,
                        x=x + width // 2,
                        y=y + height // 2,
                        width=width,
                        height=height,
                        confidence=adjusted_confidence,
                        source="ocr-grouped" if " " in text.strip() else "ocr",
                    )
                )
        return targets

    def find(self, image_path: str, names: Optional[Iterable[str]] = None):
        wanted = tuple(names or TARGET_ALIASES.keys())
        targets = self._accessibility_targets(wanted)
        targets.extend(self._ocr_targets(image_path, wanted))
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
