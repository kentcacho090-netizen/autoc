"""Interactive terminal UI for AutoC.

Designed for Termux: no browser, Flask, or web server is required.
"""
import json
import os
import time

from bot_service import BotService
from engine import AndroidController
from vision import ScreenDetector

BASE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE, "settings.json")
CONFIG_FILE = os.path.join(BASE, "detector_config.json")


def clear():
    os.system("clear")


def load_settings():
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def yn(value):
    return "ON" if value else "OFF"


def banner(status="STOPPED"):
    clear()
    print("\033[92m" + r"""
 █████╗ ██╗   ██╗████████╗ ██████╗
██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗
███████║██║   ██║   ██║   ██║   ██║
██╔══██║██║   ██║   ██║   ██║   ██║
██║  ██║╚██████╔╝   ██║   ╚██████╔╝
╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝
""" + "\033[0m")
    print("              SMART AUTOMATION")
    print("              Terminal Edition")
    print("=" * 62)
    print(f" Status       : {status}")
    print(f" Strategy     : {load_settings().get('strategy', 'balanced').upper()}")
    print("=" * 62)


def toggle(path):
    settings = load_settings()
    obj = settings
    for key in path[:-1]:
        obj = obj[key]
    obj[path[-1]] = not obj[path[-1]]
    save_settings(settings)


def settings_menu():
    while True:
        s = load_settings()
        banner()
        print("[1] Home Village")
        print(f"    Smart upgrades  : {yn(s['home_village']['smart_upgrades'])}")
        print(f"    Smart heroes    : {yn(s['home_village']['smart_heroes'])}")
        print(f"    Smart laboratory: {yn(s['home_village']['smart_lab'])}")
        print(f"    Smart builders  : {yn(s['home_village']['smart_builders'])}")
        print(f"    Smart walls     : {yn(s['home_village']['smart_walls'])}")
        print("[2] Builder Base")
        print(f"    Smart upgrades  : {yn(s['builder_base']['smart_upgrades'])}")
        print(f"    Smart laboratory: {yn(s['builder_base']['smart_lab'])}")
        print(f"    Smart walls     : {yn(s['builder_base']['smart_walls'])}")
        print("[3] Farming")
        print(f"    Smart farming   : {yn(s['farming']['enabled'])}")
        print(f"    Max skips       : {s['farming']['max_opponent_skips']}")
        print("[4] Strategy")
        print("[5] Timing")
        print("[0] Back")
        choice = input("\nChoose : ").strip()
        if choice == "0":
            return
        if choice == "1":
            sub_toggle([("smart_upgrades", "Smart upgrades"), ("smart_heroes", "Smart heroes"), ("smart_lab", "Smart laboratory"), ("smart_builders", "Smart builders"), ("smart_walls", "Smart walls")], "home_village")
        elif choice == "2":
            sub_toggle([("smart_upgrades", "Smart upgrades"), ("smart_lab", "Smart laboratory"), ("smart_walls", "Smart walls")], "builder_base")
        elif choice == "3":
            s = load_settings(); s['farming']['enabled'] = not s['farming']['enabled']
            value = input("Max opponent skips (Enter keeps current): ").strip()
            if value.isdigit(): s['farming']['max_opponent_skips'] = min(100, int(value))
            save_settings(s)
        elif choice == "4":
            s = load_settings()
            value = input("Strategy [balanced/progression/conservative] : ").strip().lower()
            if value in {"balanced", "progression", "conservative"}: s['strategy'] = value
            save_settings(s)
        elif choice == "5":
            s = load_settings()
            value = input(f"Cycle delay seconds [{s['timing']['cycle_delay']}] : ").strip()
            if value.isdigit(): s['timing']['cycle_delay'] = max(1, int(value))
            save_settings(s)


def sub_toggle(items, section):
    s = load_settings()
    while True:
        banner()
        print(f"--- {section.replace('_', ' ').title()} ---")
        for i, (key, label) in enumerate(items, 1):
            print(f"[{i}] {label:<20}: {yn(s[section][key])}")
        print("[0] Back")
        choice = input("\nChoose : ").strip()
        if choice == "0": return
        if choice.isdigit() and 1 <= int(choice) <= len(items):
            key = items[int(choice) - 1][0]
            s[section][key] = not s[section][key]
            save_settings(s)


def run_test():
    banner("TEST")
    controller = AndroidController()
    print("Android control:", "READY" if controller.check_connection() else "FAILED")
    path = controller.take_screenshot("autoc_test.png")
    if not path:
        print("Screenshot: FAILED")
        input("\nPress Enter...")
        return
    try:
        regions = load_regions()
        observation = ScreenDetector(controller, regions).observe(path)
        print("Screenshot: OK")
        print("Village   :", observation.village)
        print("Resources :", observation.resources)
        print("OCR       :", observation.text[:500] or "(none)")
        print("Confidence:", f"{observation.confidence:.0%}")
    except Exception as exc:
        print("Vision test error:", exc)
    input("\nPress Enter...")


def load_regions():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("regions", {})
    except (OSError, ValueError):
        return {}


def main():
    bot = BotService(SETTINGS_FILE)
    while True:
        banner("RUNNING" if bot.running else "STOPPED")
        print("[1] Start / Stop Bot")
        print("[2] Smart Automation Settings")
        print("[3] Test Android + Screenshot + OCR")
        print("[4] Reload Settings")
        print("[Q] Exit")
        choice = input("\nChoose : ").strip().lower()
        if choice == "1":
            bot.toggle()
            time.sleep(1)
        elif choice == "2":
            settings_menu()
            bot.reload()
        elif choice == "3":
            run_test()
        elif choice == "4":
            bot.reload()
        elif choice == "q":
            bot.stop()
            print("AutoC closed.")
            return


if __name__ == "__main__":
    main()
