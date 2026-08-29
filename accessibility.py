"""Dynamic Android UI hierarchy inspection for AutoC.

The accessibility hierarchy provides text, content descriptions, resource IDs,
and screen bounds without relying on fixed coordinates.  It is used as a
second perception channel alongside screenshot OCR.  Bounds are treated as
candidate locations only; the action layer must still verify the current
screen before tapping.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import shutil
import subprocess
import tempfile
from typing import Iterable, Optional
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class AccessibilityNode:
    text: str
    content_description: str
    resource_id: str
    class_name: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    enabled: bool

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    @property
    def searchable_text(self) -> str:
        return " ".join(
            part for part in (self.text, self.content_description, self.resource_id) if part
        )


class AccessibilityInspector:
    """Read the current Android UI hierarchy using uiautomator."""

    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    @staticmethod
    def _parse_bool(value: str) -> bool:
        return value.strip().lower() == "true"

    @staticmethod
    def _parse_bounds(value: str) -> Optional[tuple[int, int, int, int]]:
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value.strip())
        if not match:
            return None
        left, top, right, bottom = map(int, match.groups())
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom

    @classmethod
    def _parse_xml(cls, xml_text: str) -> list[AccessibilityNode]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        nodes: list[AccessibilityNode] = []
        for element in root.iter("node"):
            bounds = cls._parse_bounds(element.attrib.get("bounds", ""))
            if bounds is None:
                continue
            node = AccessibilityNode(
                text=element.attrib.get("text", "").strip(),
                content_description=element.attrib.get("content-desc", "").strip(),
                resource_id=element.attrib.get("resource-id", "").strip(),
                class_name=element.attrib.get("class", "").strip(),
                bounds=bounds,
                clickable=cls._parse_bool(element.attrib.get("clickable", "false")),
                enabled=cls._parse_bool(element.attrib.get("enabled", "true")),
            )
            if node.enabled and node.searchable_text:
                nodes.append(node)
        return nodes

    def dump(self) -> list[AccessibilityNode]:
        if not shutil.which("su") and not shutil.which("sh"):
            return []

        remote = "/sdcard/autoc_ui.xml"
        command = f"uiautomator dump --compressed {remote} >/dev/null 2>&1 && cat {remote}"
        runners = []
        if shutil.which("su"):
            runners.append(["su", "-c", command])
        runners.append(["sh", "-c", command])

        for args in runners:
            try:
                result = subprocess.run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode == 0 and "<hierarchy" in result.stdout:
                return self._parse_xml(result.stdout)
        return []

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def find(self, names: Iterable[str]) -> list[AccessibilityNode]:
        wanted = [self._normalize(name) for name in names if name]
        if not wanted:
            return []
        matches: list[AccessibilityNode] = []
        for node in self.dump():
            haystack = self._normalize(node.searchable_text)
            if any(term in haystack for term in wanted):
                matches.append(node)
        return matches

    def best(self, name: str) -> Optional[AccessibilityNode]:
        matches = self.find((name,))
        if not matches:
            return None
        return max(
            matches,
            key=lambda node: (
                1 if node.clickable else 0,
                len(node.searchable_text),
                node.bounds[2] - node.bounds[0],
            ),
        )
