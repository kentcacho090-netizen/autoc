import json
import threading
import time

from engine import ADBController
from strategy import AccountState, SmartPlanner
from vision import ScreenDetector


class BotService:
    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.running = False
        self._thread = None
        self.last_observation = {"village": "unknown", "resources": {}, "text": "", "confidence": 0, "source": "none"}
        self.last_decision = {"action": "idle", "reason": "Bot has not observed the screen yet."}
        self.reload()

    def reload(self):
        with open(self.settings_file, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        self.planner = SmartPlanner(self.settings.get("strategy", "balanced"))
        detector_file = self.settings.get("detector_config", "detector_config.json")
        try:
            with open(detector_file, "r", encoding="utf-8") as f:
                detector_config = json.load(f)
        except (OSError, json.JSONDecodeError):
            detector_config = {"regions": {}}
        self.detector_regions = detector_config.get("regions", {})

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def status(self):
        return {
            "running": self.running,
            "observation": self.last_observation,
            "decision": self.last_decision,
        }

    def _state_from_observation(self, observation):
        resources = observation.resources
        return AccountState(
            village=observation.village,
            gold=resources.get("gold") or 0,
            elixir=resources.get("elixir") or 0,
            dark_elixir=resources.get("dark_elixir") or 0,
        )

    def run(self):
        controller = ADBController()
        detector = ScreenDetector(controller, self.detector_regions)
        while self.running:
            if not controller.check_connection():
                self.last_decision = {"action": "wait", "reason": "Android control is unavailable."}
                time.sleep(5)
                continue

            observation = detector.observe()
            self.last_observation = observation.to_dict()

            # Decision only: no blind taps. Actions will be enabled after each
            # action has a dedicated, verified detector/handler.
            state = self._state_from_observation(observation)
            decision = self.planner.choose(state)
            self.last_decision = {"action": decision.action, "reason": decision.reason}
            print(f"[Vision] village={observation.village} confidence={observation.confidence:.2f}")
            print(f"[Planner] {decision.action}: {decision.reason}")
            time.sleep(max(1, int(self.settings["timing"].get("cycle_delay", 10))))
