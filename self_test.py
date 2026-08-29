"""Run before touching the game: python self_test.py"""
from __future__ import annotations

import importlib
import shutil
import sys


def main() -> int:
    print("AUTO self-test")
    print("=" * 40)

    failures = []
    for module in ("config", "engine", "vision"):
        try:
            importlib.import_module(module)
            print(f"[OK] import {module}")
        except Exception as exc:
            failures.append(f"import {module}: {exc}")
            print(f"[FAIL] import {module}: {exc}")

    try:
        from vision import ScreenDetector
        cases = {
            "7832": 7832,
            "10,640": 10640,
            "7.8K": 7800,
            "2M": 2_000_000,
            "": None,
            "mm7": None,
        }
        for raw, expected in cases.items():
            got = ScreenDetector.parse_number(raw)
            if got != expected:
                failures.append(f"parse_number({raw!r}) -> {got!r}, expected {expected!r}")
        print("[OK] OCR number parser")
    except Exception as exc:
        failures.append(f"OCR parser test: {exc}")
        print(f"[FAIL] OCR parser test: {exc}")

    if shutil.which("adb"):
        print("[OK] adb found")
    else:
        print("[WARN] adb not found in PATH (install Android platform-tools before running AUTO)")

    if shutil.which("tesseract"):
        print("[OK] tesseract found")
    else:
        print("[WARN] tesseract not found in PATH (OCR will not work until installed)")

    print("=" * 40)
    if failures:
        print("SELF-TEST FAILED")
        for failure in failures:
            print(" -", failure)
        return 1
    print("SELF-TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
