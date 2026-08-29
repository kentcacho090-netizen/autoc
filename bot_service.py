import json
import threading
import time

from engine import ADBController
from strategy import AccountState, SmartPlanner


class BotService:
    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.running = False
        self._thread = None
        self.reload()

    def reload(self):
        with open(self.settings_file, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        self.planner = SmartPlanner(self.settings.get("strategy", "balanced"))

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

    def run(self):
        controller = ADBController()
        while self.running:
            # The controller is ready for Android interaction, but the planner
            # only acts on confirmed state. Detection/recognition is the next
            # layer and should supply a real AccountState here.
            if not controller.check_connection():
                time.sleep(5)
                continue

            state = AccountState(village="home")
            decision = self.planner.choose(state)
            print(f"[Planner] {decision.action}: {decision.reason}")
            time.sleep(max(1, int(self.settings["timing"].get("cycle_delay", 10))))
