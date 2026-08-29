"""Human-readable diagnostic report generation for AutoC.

This module converts the latest local diagnostic JSON into a compact report that
can be inspected on the Android device after an unattended run. It performs no
network access and never executes Android commands.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict


class DiagnosticReporter:
    """Read the latest diagnostic snapshot and produce a stable text report."""

    def __init__(self, directory: str = "diagnostics") -> None:
        self.directory = directory
        self.latest_path = os.path.join(directory, "latest.json")
        self.report_path = os.path.join(directory, "report.txt")

    def load(self) -> Dict[str, Any]:
        if not os.path.isfile(self.latest_path):
            return {}
        try:
            with open(self.latest_path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _resource_line(resources: Any) -> str:
        if not isinstance(resources, dict):
            return "Resources : unavailable"
        names = ("gold", "elixir", "dark_elixir", "gems")
        parts = []
        for name in names:
            value = resources.get(name)
            parts.append(f"{name}={value if value is not None else 'unknown'}")
        return "Resources : " + " | ".join(parts)

    def render(self, data: Dict[str, Any] | None = None) -> str:
        payload = data if data is not None else self.load()
        observation = payload.get("observation") or {}
        decision = payload.get("decision") or {}
        progress = payload.get("progress") or {}
        error = payload.get("error")

        timestamp = payload.get("timestamp")
        if isinstance(timestamp, (int, float)):
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        else:
            stamp = "unknown"

        lines = [
            "AutoC Diagnostic Report",
            "=" * 24,
            f"Timestamp : {stamp}",
            f"Village   : {observation.get('village', 'unknown')}",
            f"Screen    : {observation.get('screen_size', 'unknown')}",
            f"Confidence: {observation.get('confidence', 'unknown')}",
            self._resource_line(observation.get("resources")),
            f"Action    : {decision.get('action', 'unknown')}",
            f"Reason    : {decision.get('reason', 'unknown')}",
            f"Phase     : {progress.get('phase', 'unknown')}",
            f"Cycles    : {progress.get('cycles', 'unknown')}",
            f"Successes : {progress.get('actions_succeeded', 'unknown')}",
            f"Refused   : {progress.get('actions_refused', 'unknown')}",
            f"Errors    : {progress.get('errors', 'unknown')}",
            f"Error     : {error or 'none'}",
            "",
        ]
        return "\n".join(lines)

    def write(self) -> str:
        os.makedirs(self.directory, exist_ok=True)
        temporary = self.report_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(self.render())
        os.replace(temporary, self.report_path)
        return self.report_path


if __name__ == "__main__":
    path = DiagnosticReporter().write()
    print(path)
