"""Local diagnostic bundle support for AutoC.

The diagnostic writer keeps the feedback loop local to the Android device.
It writes small, human-readable JSON metadata next to the latest screenshot.
No network service or credentials are required.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping, Optional


class DiagnosticStore:
    """Persist the latest observation, decision, and progress locally."""

    def __init__(self, directory: str = "diagnostics") -> None:
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def write(
        self,
        observation: Optional[Mapping[str, Any]] = None,
        decision: Optional[Mapping[str, Any]] = None,
        progress: Optional[Mapping[str, Any]] = None,
        error: Optional[str] = None,
    ) -> str:
        payload = {
            "timestamp": int(time.time()),
            "observation": dict(observation or {}),
            "decision": dict(decision or {}),
            "progress": dict(progress or {}),
            "error": error,
        }
        path = os.path.join(self.directory, "latest.json")
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
        return path
