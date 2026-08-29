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
        self.last_observation = None
        self.last_decision = None
        self.reload()

    def reload(self):
        with open(self.settings_file, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        self.planner = SmartPlanner(self.settings.get("strategy", "balanced"))

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def _state_from_observation(self, observation):
        r = observation.resources
        return AccountState(
            village=observation.village,
            gold=r.get("gold"),
            elixir=r.get("elixir"),
            dark_elixir=r.get("dark_elixir"),
            confidence=observation.confidence,
        )

    def run(self):
        controller = ADBController()
        detector = ScreenDetector(controller, self.settings.get("detector_config", "detector_config.json"))
        while self.running:
            if not controller.check_connection():
                time.sleep(5)
                continue

            observation = detector.observe()
            self.last_observation = observation.to_dict()
            state = self._state_from_observation(observation)
            decision = self.planner.choose(state)
            self.last_decision = {"action": decision.action, "reason": decision.reason, "safe": decision.safe}
            print(f"[Vision] {observation.village} confidence={observation.confidence:.2f} resources={observation.resources}")
            print(f"[Planner] {decision.action}: {decision.reason}")

            # This stage observes and plans only. Actual game actions must be
            # implemented against verified UI states rather than guessed taps.
            delay = max(1, int(self.settings.get("timing", {}).get("cycle_delay", 10)))
            time.sleep(delay)
