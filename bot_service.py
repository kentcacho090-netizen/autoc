import json
import threading
import time

from engine import ADBController
from strategy import AccountState, SmartPlanner
from automation_state import SmartAutomationStateMachine
from vision import ScreenDetector


class BotService:
    """Long-running smart loop.

    Perception and planning run continuously, but the action gate refuses any
    tap unless a future vision detector supplies a verified target.  This keeps
    the bot from repeating the fixed-coordinate Town Hall mistake while the
    dynamic object detectors are being added.
    """

    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.running = False
        self._thread = None
        self.last_observation = None
        self.last_decision = None
        self.last_phase = "observe"
        self.reload()

    def reload(self):
        with open(self.settings_file, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        threshold = float(self.settings.get("vision", {}).get("confidence_threshold", 0.70))
        self.planner = SmartPlanner(self.settings.get("strategy", "balanced"), threshold)
        self.machine = SmartAutomationStateMachine(
            min_target_confidence=max(0.80, threshold),
            max_failures=int(self.settings.get("vision", {}).get("max_action_failures", 3)),
        )

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
        detector = ScreenDetector(
            controller,
            self.settings.get("detector_config", "detector_config.json"),
        )

        while self.running:
            try:
                self.machine.state.phase = self.machine.state.phase.OBSERVE

                if not controller.check_connection():
                    self.last_phase = "recover"
                    time.sleep(5)
                    continue

                observation = detector.observe()
                self.last_observation = observation.to_dict()
                state = self._state_from_observation(observation)
                decision = self.planner.choose(state)
                self.last_decision = {
                    "action": decision.action,
                    "reason": decision.reason,
                    "safe": decision.safe,
                }

                # Dynamic targets will be supplied by the object/template
                # detector.  An empty target map intentionally means no tap.
                action = self.machine.plan_action(decision, targets={})
                self.last_phase = self.machine.state.phase.value

                print(
                    f"[Vision] village={observation.village} "
                    f"confidence={observation.confidence:.2f} "
                    f"resources={observation.resources}"
                )
                print(
                    f"[Planner] {decision.action}: {decision.reason} "
                    f"safe={decision.safe}"
                )
                print(f"[ActionGate] {action.name}: {action.reason}")

                # No guessed coordinates. Once dynamic perception supplies a
                # verified target, this gate is where execution will occur.
                if action.target is not None and self.machine.before_action(action):
                    controller.tap(*action.target.center)

                delay = max(1, int(self.settings.get("timing", {}).get("cycle_delay", 10)))
                time.sleep(delay)
            except Exception as exc:
                self.machine.after_action(False, str(exc))
                self.last_phase = self.machine.state.phase.value
                print(f"[Bot] Recovered from cycle error: {exc}")
                time.sleep(2)
