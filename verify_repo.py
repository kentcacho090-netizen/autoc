"""Offline repository verification for AutoC.

This verifier checks imports, resource parsing, Town Hall parsing, and the
resource HUD configuration without touching Android. It is deterministic and
safe to run in Termux before a device test.
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
    "strategy",
    "townhall",
    "runtime_patch",
    "bot_service",
    "ui_targets",
    "verified_actions",
    "diagnostics",
    "diagnostic_report",
)


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


def main() -> int:
    print("AutoC repository verification")
    print(f"Python: {sys.version.split()[0]}")

    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:
            fail(f"import {name}: {type(exc).__name__}: {exc}")
        print(f"[PASS] import {name}")

    from vision import ScreenDetector
    from townhall import TownHallProbe

    number_cases = {
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
    for raw, expected in number_cases.items():
        actual = ScreenDetector.parse_number(raw)
        if actual != expected:
            fail(f"parse_number({raw!r}) -> {actual!r}, expected {expected!r}")
    print("[PASS] resource-number parser")

    townhall_cases = {
        "Town Hall 7": (7, 0.98),
        "Town Hall Level 12": (12, 0.98),
        "townhall 15": (15, 0.98),
        "TH 9": (9, 0.98),
        "Town Hall": (None, 0.0),
        "Town Hall 21": (None, 0.0),
        "random 7": (None, 0.0),
    }
    for raw, expected in townhall_cases.items():
        actual = TownHallProbe._parse_level(raw)
        if actual != expected:
            fail(f"_parse_level({raw!r}) -> {actual!r}, expected {expected!r}")
    print("[PASS] Town Hall parser")

    detector_config = ROOT / "detector_config.json"
    if detector_config.exists():
        try:
            with detector_config.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
            if not isinstance(value, dict):
                fail("detector_config.json is not a JSON object")
            resources = value.get("resources", {})
            if not isinstance(resources, dict):
                fail("resources config is not an object")
            required = {"gold", "elixir", "dark_elixir"}
            missing = required - resources.keys()
            if missing:
                fail(f"resource regions missing: {sorted(missing)}")
            for name in required:
                region = resources[name].get("region", {})
                if not all(key in region for key in ("x", "y", "width", "height")):
                    fail(f"resource region incomplete: {name}")
                if not (0 < float(region["width"]) <= 1 and 0 < float(region["height"]) <= 1):
                    fail(f"resource region dimensions invalid: {name}")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            fail(f"detector_config.json: {exc}")
        print("[PASS] detector_config.json")

    print("[PASS] offline verification complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
