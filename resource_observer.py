"""Dynamic resource-value extraction for AutoC.

Resource values are discovered from the current screenshot rather than fixed
pixel rectangles. OCR word boxes are grouped by visual line, numeric tokens
are normalized, and candidates are scored from their geometry and OCR
confidence. The reader never emits a value when the evidence is ambiguous.
"""
from __future__ import annotations

from dataclasses import dataclass
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
class ResourceCandidate:
    value: int
    raw: str
    x: int
    y: int
    width: int
    height: int
    confidence: float


@dataclass(frozen=True)
class ResourceReading:
    values: dict[str, Optional[int]]
    confidence: dict[str, float]
    candidates: tuple[ResourceCandidate, ...]
    source: str


class DynamicResourceObserver:
    """Read the four main HUD values without assuming a fixed HUD rectangle."""

    ORDER = ("gold", "elixir", "dark_elixir", "gems")

    def __init__(self, tesseract_binary: str = "tesseract", min_confidence: float = 0.35) -> None:
        self.tesseract_binary = tesseract_binary
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))

    @staticmethod
    def _parse_number(text: str) -> Optional[int]:
        raw = str(text).strip().upper()
        raw = raw.replace("O", "0").replace("I", "1").replace("L", "1")
        raw = re.sub(r"\s+", "", raw)
        raw = re.sub(r"[^0-9KMB,\.]+", "", raw)
        if not raw or raw.startswith("-"):
            return None
        suffix = raw[-1] if raw[-1] in "KMB" else ""
        token = raw[:-1] if suffix else raw
        if not token or not re.fullmatch(r"\d[\d,.]*", token):
            return None
        try:
            if suffix:
                decimal = token.replace(",", ".")
                if decimal.count(".") > 1:
                    parts = decimal.split(".")
                    decimal = parts[0] + "." + "".join(parts[1:])
                return int(round(float(decimal) * {"K": 10**3, "M": 10**6, "B": 10**9}[suffix]))
            return int(token.replace(",", "").replace(".", ""))
        except (ValueError, OverflowError):
            return None

    def _ocr_rows(self, image_path: str) -> list[tuple[str, int, int, int, int, float]]:
        if Image is None or not shutil.which(self.tesseract_binary):
            return []
        temporary = None
        try:
            with Image.open(image_path) as image:
                rgb = image.convert("RGB")
                fd, temporary = tempfile.mkstemp(suffix=".png")
                import os
                os.close(fd)
                rgb.save(temporary, format="PNG")
            result = subprocess.run(
                [self.tesseract_binary, temporary, "stdout", "--psm", "11", "tsv"],
                capture_output=True,
                text=True,
                timeout=12,
                check=False,
            )
            if result.returncode != 0:
                return []
            rows: list[tuple[str, int, int, int, int, float]] = []
            for line in result.stdout.splitlines()[1:]:
                columns = line.split("\t")
                if len(columns) < 12:
                    continue
                try:
                    confidence = float(columns[10]) / 100.0
                    text = columns[11].strip()
                    x, y, width, height = map(int, columns[6:10])
                except (ValueError, IndexError):
                    continue
                if text and width > 2 and height > 3 and confidence >= self.min_confidence:
                    rows.append((text, x, y, width, height, confidence))
            return rows
        except (OSError, subprocess.SubprocessError):
            return []
        finally:
            if temporary:
                try:
                    import os
                    os.unlink(temporary)
                except OSError:
                    pass

    @staticmethod
    def _numeric_text(text: str) -> bool:
        return bool(re.fullmatch(r"[0-9OILoilkmbKMB,\.]+", text.strip()))

    @classmethod
    def _join_numeric_tokens(cls, rows: Iterable[tuple[str, int, int, int, int, float]]) -> list[tuple[str, int, int, int, int, float]]:
        numeric = [row for row in rows if cls._numeric_text(row[0])]
        numeric.sort(key=lambda row: (row[2], row[1]))
        merged: list[tuple[str, int, int, int, int, float]] = []
        for row in numeric:
            if not merged:
                merged.append(row)
                continue
            previous = merged[-1]
            prev_right = previous[1] + previous[3]
            vertical = max(0, min(previous[2] + previous[4], row[2] + row[4]) - max(previous[2], row[2]))
            overlap = vertical / max(1, min(previous[4], row[4]))
            gap = row[1] - prev_right
            if overlap >= 0.45 and 0 <= gap <= max(18, int(min(previous[4], row[4]) * 1.25)):
                text = previous[0] + row[0]
                left = min(previous[1], row[1])
                top = min(previous[2], row[2])
                right = max(previous[1] + previous[3], row[1] + row[3])
                bottom = max(previous[2] + previous[4], row[2] + row[4])
                confidence = min(previous[5], row[5])
                merged[-1] = (text, left, top, right - left, bottom - top, confidence)
            else:
                merged.append(row)
        return merged

    def read(self, image_path: str) -> ResourceReading:
        rows = self._ocr_rows(image_path)
        if not rows:
            return ResourceReading({name: None for name in self.ORDER}, {name: 0.0 for name in self.ORDER}, (), "tesseract-unavailable-or-empty")
        try:
            with Image.open(image_path) as image:
                width, height = image.size
        except (OSError, AttributeError):
            return ResourceReading({name: None for name in self.ORDER}, {name: 0.0 for name in self.ORDER}, (), "invalid-image")

        candidates: list[ResourceCandidate] = []
        for text, x, y, box_width, box_height, ocr_confidence in self._join_numeric_tokens(rows):
            value = self._parse_number(text)
            if value is None or value < 0 or value > 2_000_000_000:
                continue
            right_bias = x / max(1, width)
            hud_bias = min(1.0, max(0.0, (right_bias - 0.55) / 0.45))
            size_score = min(1.0, box_width / max(1.0, width * 0.03))
            confidence = min(1.0, 0.65 * ocr_confidence + 0.25 * hud_bias + 0.10 * size_score)
            candidates.append(ResourceCandidate(value, text, x, y, box_width, box_height, confidence))

        candidates.sort(key=lambda candidate: (-candidate.confidence, candidate.y, candidate.x))
        selected: dict[str, ResourceCandidate] = {}
        if candidates:
            right_candidates = [candidate for candidate in candidates if candidate.x / max(1, width) >= 0.55]
            pool = right_candidates or candidates
            pool.sort(key=lambda candidate: candidate.y)
            if len(pool) >= 4:
                selected = {name: pool[index] for index, name in enumerate(self.ORDER)}
            else:
                for index, candidate in enumerate(pool[:4]):
                    selected[self.ORDER[index]] = candidate

        values = {name: (selected[name].value if name in selected else None) for name in self.ORDER}
        confidence = {name: (selected[name].confidence if name in selected else 0.0) for name in self.ORDER}
        return ResourceReading(values, confidence, tuple(candidates), "dynamic-ocr-geometry")
