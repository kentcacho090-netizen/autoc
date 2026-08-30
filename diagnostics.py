"""Local diagnostic bundle support for AutoC."""
from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping, Optional


class DiagnosticStore:
    """Persist the latest observation, decision, progress, and targets locally."""

    def __init__(self, directory: str = "diagnostics") -> None:
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def write(
        self,
        observation: Optional[Mapping[str, Any]] = None,
        decision: Optional[Mapping[str, Any]] = None,
        progress: Optional[Mapping[str, Any]] = None,
        targets: Optional[Any] = None,
        phase: Optional[str] = None,
        error: Optional[str] = None,
    ) -> str:
        payload = {
            "timestamp": int(time.time()),
            "observation": dict(observation or {}),
            "decision": dict(decision or {}),
            "progress": dict(progress or {}),
            "targets": list(targets or []),
            "phase": phase,
            "error": error,
        }
        path = os.path.join(self.directory, "latest.json")
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
        return path
