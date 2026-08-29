"""Offline repository verification for AUTO.

This verifier checks imports and core parsing/planning behavior without touching
Android. It is intentionally deterministic so it can run in Termux before a
device test.
"""
from __future__ import annotations

import importlib
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent
MODULES = (
    "config",
    "engine",
    "vision",
    "planner",
    "ui_targets",
    "verified_actions",
    "diagnostics",
    "diagnostic_report",
)


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def main() -> int:
    print("AUTO repository verification")
    print(f"Python: {sys.version.split()[0]}")

    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            fail(f"import {name}: {type(exc).__name__}: {exc}")
        print(f"[PASS] import {name}")

    from vision import ScreenDetector

    cases = {
        "123": 123,
        "1,234": 1234,
        "1.234": 1234,
        "1,234,567": 1234567,
        "1.234.567": 1234567,
        "1.2K": 1200,
        "1,2K": 1200,
        "12K": 12000,
        "2.5M": 2500000,
        "2,5M": 2500000,
        "1B": 1000000000,
        "O.5M": 500000,
        "invalid": None,
        "12ABC": None,
        "-123": None,
    }
    for raw, expected in cases.items():
        actual = ScreenDetector.parse_number(raw)
        if actual != expected:
            fail(f"parse_number({raw!r}) -> {actual!r}, expected {expected!r}")
    print("[PASS] resource-number parser")

    detector_config = ROOT / "detector_config.json"
    if detector_config.exists():
        try:
            with detector_config.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, dict):
                fail("detector_config.json is not a JSON object")
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"detector_config.json: {exc}")
        print("[PASS] detector_config.json")

    print("[PASS] offline verification complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
