"""Lightweight periodic progress reporting for AutoC.

The reporter is intentionally independent of the Android controller. It keeps
only in-memory progress metadata and can be called from the bot loop without
creating another background thread.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ProgressSnapshot:
    started_at: float = field(default_factory=time.monotonic)
    cycles: int = 0
    successful_actions: int = 0
    refused_actions: int = 0
    errors: int = 0
    last_phase: str = "observe"
    last_action: str = "none"
    last_error: Optional[str] = None
    last_report_at: float = field(default_factory=time.monotonic)

    def uptime_seconds(self) -> int:
        return max(0, int(time.monotonic() - self.started_at))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "uptime_seconds": self.uptime_seconds(),
            "cycles": self.cycles,
            "successful_actions": self.successful_actions,
            "refused_actions": self.refused_actions,
            "errors": self.errors,
            "last_phase": self.last_phase,
            "last_action": self.last_action,
            "last_error": self.last_error,
        }


class ProgressReporter:
    def __init__(self, interval_seconds: float = 60.0):
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.snapshot = ProgressSnapshot()

    def cycle_started(self, phase: str = "observe") -> None:
        self.snapshot.cycles += 1
        self.snapshot.last_phase = phase

    def action_refused(self, reason: str) -> None:
        self.snapshot.refused_actions += 1
        self.snapshot.last_action = "refused"
        self.snapshot.last_error = reason

    def action_succeeded(self, action: str) -> None:
        self.snapshot.successful_actions += 1
        self.snapshot.last_action = action
        self.snapshot.last_error = None

    def error(self, message: str) -> None:
        self.snapshot.errors += 1
        self.snapshot.last_error = message

    def maybe_report(self, force: bool = False) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        if not force and now - self.snapshot.last_report_at < self.interval_seconds:
            return None
        self.snapshot.last_report_at = now
        data = self.snapshot.as_dict()
        print(
            "[Progress] "
            f"uptime={data['uptime_seconds']}s "
            f"cycles={data['cycles']} "
            f"actions={data['successful_actions']} "
            f"refused={data['refused_actions']} "
            f"errors={data['errors']} "
            f"phase={data['last_phase']} "
            f"last={data['last_action']}"
        )
        return data
