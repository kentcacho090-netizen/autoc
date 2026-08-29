"""Verified UI-target detection for AutoC.

Targets are discovered from the current screenshot. AutoC never taps a
hard-coded coordinate through this module: a target must be visible in the
fresh screenshot and its OCR bounding box must satisfy confidence and size
checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import shutil
import subprocess
import tempfile
from typing import Iterable, List, Optional, Sequence, Tuple

try:
    from PIL import Image, ImageEnhance, ImageOps
except ImportError:
    Image = None
    ImageEnhance = None
    ImageOps = None


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
        self.confidence_threshold = max(0.0, min(1.0, float(confidence_threshold)))

    @staticmethod
    def _norm(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    @staticmethod
    def _union(words: Sequence[Tuple[str, int, int, int, int, float]]):
        x1 = min(item[1] for item in words)
        y1 = min(item[2] for item in words)
        x2 = max(item[1] + item[3] for item in words)
        y2 = max(item[2] + item[4] for item in words)
        confidence = min(item[5] for item in words)
        text = " ".join(item[0] for item in words)
        return text, x1, y1, x2 - x1, y2 - y1, confidence

    def _ocr_pass(self, image_path: str, psm: int):
        if Image is None or not shutil.which("tesseract"):
            return []
        temp = None
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
                if psm == 6 and ImageOps is not None and ImageEnhance is not None:
                    gray = ImageOps.grayscale(image)
                    image = ImageOps.autocontrast(gray)
                    image = ImageEnhance.Contrast(image).enhance(1.6)
                fd, temp = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                image.save(temp, format="PNG")

            result = subprocess.run(
                [
                    "tesseract", temp, "stdout", "--psm", str(psm), "tsv",
                    "-c", "load_system_dawg=0",
                    "-c", "load_freq_dawg=0",
                ],
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
                    block = int(cols[2])
                    paragraph = int(cols[3])
                    line_number = int(cols[4])
                    word_number = int(cols[5])
                    x, y, w, h = map(int, cols[6:10])
                    confidence = float(cols[10]) / 100.0
                    text = cols[11].strip()
                except (ValueError, IndexError):
                    continue
                if not text or confidence < self.confidence_threshold or w < 5 or h < 5:
                    continue
                rows.append((
                    block, paragraph, line_number, word_number,
                    text, x, y, w, h, confidence,
                ))
            return rows
        except (OSError, subprocess.SubprocessError):
            return []
        finally:
            if temp:
                try:
                    os.unlink(temp)
                except OSError:
                    pass

    def _ocr_data(self, image_path: str):
        """Return normalized OCR word records from two complementary passes."""
        raw = self._ocr_pass(image_path, 11)
        if not raw:
            raw = self._ocr_pass(image_path, 6)
        words = []
        for block, paragraph, line_number, word_number, text, x, y, w, h, confidence in raw:
            words.append((
                text, x, y, w, h, confidence,
                (block, paragraph, line_number), word_number,
            ))
        return words

    @staticmethod
    def _line_phrases(words):
        """Build 1-4 word phrases from OCR words on the same text line."""
        grouped = {}
        for item in words:
            text, x, y, w, h, conf, line_key, word_number = item
            grouped.setdefault(line_key, []).append(item)

        phrases = []
        for line_words in grouped.values():
            line_words.sort(key=lambda item: (item[1], item[7]))
            for start in range(len(line_words)):
                for length in range(1, min(4, len(line_words) - start) + 1):
                    selected = line_words[start:start + length]
                    phrases.append((
                        selected[0][0] if length == 1 else " ".join(item[0] for item in selected),
                        min(item[1] for item in selected),
                        min(item[2] for item in selected),
                        max(item[1] + item[3] for item in selected) - min(item[1] for item in selected),
                        max(item[2] + item[4] for item in selected) - min(item[2] for item in selected),
                        min(item[5] for item in selected),
                    ))
        return phrases

    @staticmethod
    def _match_alias(normalized: str, aliases: Sequence[str]):
        return next((alias for alias in aliases if normalized == alias), None)

    def find(self, image_path: str, names: Optional[Iterable[str]] = None):
        wanted = tuple(names or TARGET_ALIASES.keys())
        aliases = {
            name: tuple(self._norm(alias) for alias in TARGET_ALIASES.get(name, (name,)))
            for name in wanted
        }
        words = self._ocr_data(image_path)
        if not words:
            return []

        candidates = []
        for text, x, y, w, h, confidence in self._line_phrases(words):
            normalized = self._norm(text)
            for name, variants in aliases.items():
                alias = self._match_alias(normalized, variants)
                if alias is None:
                    continue
                candidates.append(UITarget(
                    name=name,
                    text=text,
                    x=x + w // 2,
                    y=y + h // 2,
                    width=w,
                    height=h,
                    confidence=confidence,
                ))

        # Remove exact duplicates produced by overlapping phrase windows or
        # multiple OCR passes while keeping the strongest observation.
        unique = {}
        for target in candidates:
            key = (target.name, target.x, target.y, self._norm(target.text))
            current = unique.get(key)
            if current is None or target.confidence > current.confidence:
                unique[key] = target

        return list(unique.values())

    def best(self, image_path: str, name: str) -> Optional[UITarget]:
        matches = [target for target in self.find(image_path, (name,)) if target.name == name]
        return max(matches, key=lambda target: target.confidence, default=None)
