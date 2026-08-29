"""AUTO - Android Clash of Clans automation entry point.

This version prioritizes reliability: connect -> launch -> screenshot ->
observe. It never blindly taps guessed coordinates. Game actions should only
be enabled after the corresponding screen has been positively detected.
"""
from __future__ import annotations

import argparse
import time

import config
from engine import ADBController, ADBError
from vision import ScreenDetector


def print_observation(obs) -> None:
    print("\n========== AUTO OBSERVATION ==========")
    print(f"Village      : {obs.village}")
    print(f"Screen       : {obs.screen_size} ({obs.orientation})")
    print(f"Gold         : {obs.resources.get('gold')}")
    print(f"Elixir       : {obs.resources.get('elixir')}")
    print(f"Dark Elixir  : {obs.resources.get('dark_elixir')}")
    print(f"Gems         : {obs.resources.get('gems')}")
    print(f"OCR          : {obs.text or '(none)'}")
    print(f"Confidence   : {obs.confidence:.0%}")
    print(f"Source       : {obs.source}")
    if obs.diagnostics:
        print(f"Diagnostics  : {obs.diagnostics}")
    print("=====================================")


def observe_once(bot: ADBController, detector: ScreenDetector):
    path = detector.capture(config.SCREENSHOT_FILE)
    obs = detector.observe(path)
    print_observation(obs)
    return obs


def main() -> int:
    parser = argparse.ArgumentParser(description="AUTO Android CoC automation")
    parser.add_argument("--once", action="store_true", help="capture and observe once, then exit")
    parser.add_argument("--loop", action="store_true", help="keep observing until Ctrl+C")
    parser.add_argument("--no-launch", action="store_true", help="do not launch Clash of Clans")
    args = parser.parse_args()

    print("AUTO - SMART AUTOMATION")
    print("Mode: OBSERVE (safe; no blind taps)\n")

    bot = ADBController(device=config.ADB_DEVICE or None)
    if not bot.check_connection():
        return 1

    try:
        if not args.no_launch:
            print(f"[Android] Launching {config.TARGET_PACKAGE}...")
            bot.launch(config.TARGET_PACKAGE)

        detector = ScreenDetector(bot, config.DETECTOR_CONFIG)
        observe_once(bot, detector)

        if args.once:
            return 0

        # Default to loop mode so `python main.py` remains useful.
        print(f"[System] Rechecking every {config.OBSERVE_INTERVAL:.1f}s. Press Ctrl+C to stop.")
        while True:
            time.sleep(config.OBSERVE_INTERVAL)
            observe_once(bot, detector)

    except KeyboardInterrupt:
        print("\n[System] Stopped by user.")
        return 0
    except (ADBError, OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:
        # Keep unexpected failures visible without dumping an unreadable crash.
        print(f"[ERROR] Unexpected failure: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
