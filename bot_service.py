import json
import threading
import time

from engine import ADBController
from strategy import AccountState, SmartPlanner
from automation_state import SmartAutomationStateMachine
from progress import ProgressReporter
from vision import ScreenDetector


class BotService:
    """Long-running smart loop with safe action gating and progress reporting."""

    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.running = False
        self._thread = None
        self.last_observation = None
        self.last_decision = None
        self.last_phase = "observe"
        self.progress = ProgressReporter(interval_seconds=60.0)
        self.reload()

    def reload(self):
        with open(self.settings_file, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        vision = self.settings.get("vision", {})
        threshold = float(vision.get("confidence_threshold", 0.70))
        self.planner = SmartPlanner(self.settings.get("strategy", "balanced"), threshold)
        self.machine = SmartAutomationStateMachine(
            min_target_confidence=max(0.80, threshold),
            max_failures=max(1, int(vision.get("max_action_failures", 3))),
        )

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        if self.running:
            return
        interval = self.settings.get("vision", {}).get("progress_interval_seconds", 60)
        self.progress = ProgressReporter(interval_seconds=interval)
        self.running = True
        self._thread = threading.Thread(target=self.run, name="autoc-bot", daemon=True)
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
            self.progress.cycle_started("observe")
            try:
                if not controller.check_connection():
                    self.last_phase = "recover"
                    self.progress.error("Android control unavailable")
                    self.progress.maybe_report()
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

                # The planner decides categories. Until a verified object
                # detector identifies a matching on-screen target, no tap is
                # permitted. This prevents fixed-coordinate game actions.
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

                if action.target is None:
                    self.progress.action_refused(action.reason or "No verified target")
                elif self.machine.before_action(action):
                    result = controller.tap(*action.target.center)
                    verified = result is not None
                    self.machine.after_action(verified, None if verified else "Android tap failed")
                    self.last_phase = self.machine.state.phase.value
                    if verified:
                        self.progress.action_succeeded(action.name)
                    else:
                        self.progress.error("Android tap failed")
                else:
                    self.progress.action_refused(action.reason or "Action gate refused target")

                self.progress.maybe_report()
                delay = max(1, int(self.settings.get("timing", {}).get("cycle_delay", 10)))
                time.sleep(delay)
            except Exception as exc:
                self.machine.after_action(False, str(exc))
                self.last_phase = self.machine.state.phase.value
                self.progress.error(str(exc))
                self.progress.maybe_report()
                print(f"[Bot] Recovered from cycle error: {exc}")
                time.sleep(2)

        self.progress.maybe_report(force=True)
