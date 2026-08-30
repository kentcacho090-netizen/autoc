"""Evidence-driven detection of optional Clash of Clans features.

The detector distinguishes "not observed" from "locked". Optional systems
become eligible only after current-screen evidence establishes that the
feature exists. Absence is never treated as proof of a lock or unlock.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Optional


@dataclass(frozen=True)
class FeatureEvidence:
    feature: str
    unlocked: bool
    confidence: float
    matched_terms: tuple[str, ...] = ()
    source: str = "unknown"


@dataclass(frozen=True)
class FeatureUnlockState:
    dark_elixir: Optional[FeatureEvidence] = None
    builder_base: Optional[FeatureEvidence] = None

    @property
    def dark_elixir_unlocked(self) -> bool:
        return bool(self.dark_elixir and self.dark_elixir.unlocked)

    @property
    def builder_base_unlocked(self) -> bool:
        return bool(self.builder_base and self.builder_base.unlocked)


class FeatureUnlockDetector:
    """Classify explicit feature evidence from fresh screen text."""

    _DARK_TERMS = (
        "dark elixir",
        "dark elixir storage",
        "dark spell",
        "dark barracks",
        "dark drill",
    )
    # Avoid generic home-village labels such as "Elixir Collector".
    _BUILDER_TERMS = (
        "builder base",
        "builder hall",
        "builder hut",
        "builder gold",
        "builder elixir",
        "clock tower",
    )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _evidence(
        self,
        feature: str,
        text: str,
        terms: Iterable[str],
        source: str,
    ) -> Optional[FeatureEvidence]:
        normalized = self._normalize(text)
        if not normalized:
            return None
        matched = tuple(
            term for term in terms
            if self._normalize(term) in normalized
        )
        if not matched:
            return None
        confidence = min(0.99, 0.82 + 0.08 * (len(matched) - 1))
        return FeatureEvidence(
            feature=feature,
            unlocked=True,
            confidence=confidence,
            matched_terms=matched,
            source=source,
        )

    def detect(
        self,
        ocr_text: str = "",
        accessibility_text: str = "",
    ) -> FeatureUnlockState:
        dark_ocr = self._evidence("dark_elixir", ocr_text, self._DARK_TERMS, "ocr")
        builder_ocr = self._evidence("builder_base", ocr_text, self._BUILDER_TERMS, "ocr")
        dark_acc = self._evidence("dark_elixir", accessibility_text, self._DARK_TERMS, "accessibility")
        builder_acc = self._evidence("builder_base", accessibility_text, self._BUILDER_TERMS, "accessibility")
        return FeatureUnlockState(
            dark_elixir=self._prefer(dark_ocr, dark_acc),
            builder_base=self._prefer(builder_ocr, builder_acc),
        )

    @staticmethod
    def _prefer(
        first: Optional[FeatureEvidence],
        second: Optional[FeatureEvidence],
    ) -> Optional[FeatureEvidence]:
        if first is None:
            return second
        if second is None:
            return first
        return first if first.confidence >= second.confidence else second
