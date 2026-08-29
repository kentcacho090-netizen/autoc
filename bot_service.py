import json
import threading
import time

from engine import ADBController
from strategy import AccountState, SmartPlanner
from automation_state import SmartAutomationStateMachine, Target
from progress import ProgressReporter
from ui_targets import UITargetDetector
from vision import ScreenDetector


class BotService:
    """Long-running smart loop with dynamic perception and safe action gating."""

    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.running = False
        self._thread = None
        self.last_observation = None
        self.last_decision = None
        self.last_targets = []
        self.last_phase = "observe"
        self.progress = ProgressReporter(interval_seconds=60.0)
        self.reload()

    def reload(self):
        with open(self.settings_file, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        vision_settings = self.settings.get("vision", {})
        threshold = float(vision_settings.get("confidence_threshold", 0.70))
        progress_interval = max(1.0, float(vision_settings.get("progress_interval_seconds", 60)))
        self.planner = SmartPlanner(self.settings.get("strategy", "balanced"), threshold)
        self.machine = SmartAutomationStateMachine(
            min_target_confidence=max(0.80, float(vision_settings.get("target_confidence_threshold", threshold))),
            max_failures=int(vision_settings.get("max_action_failures", 3)),
        )
        self.progress_interval = progress_interval

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        if self.running:
            return
        self.progress = ProgressReporter(interval_seconds=self.progress_interval)
        self.running = True
        self._thread = threading.Thread(target=self.run, name="autoc-bot", daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False

    def _state_from_observation(self, observation):
        resources = observation.resources
        return AccountState(
            village=observation.village,
            gold=resources.get("gold"),
            elixir=resources.get("elixir"),
            dark_elixir=resources.get("dark_elixir"),
            confidence=observation.confidence,
        )

    @staticmethod
    def _target_map(detected_targets):
        """Convert dynamic UI detections into state-machine targets."""
        result = {}
        for detected in detected_targets:
            target = Target(
                name=detected.name,
                center=detected.center,
                confidence=detected.confidence,
                source=detected.source,
            )
            previous = result.get(detected.name)
            if previous is None or target.confidence > previous.confidence:
                result[detected.name] = target
        return result

    def run(self):
        controller = ADBController()
        screen_detector = ScreenDetector(
            controller,
            self.settings.get("detector_config", "detector_config.json"),
        )
        ui_detector = UITargetDetector(
            confidence_threshold=float(
                self.settings.get("vision", {}).get("target_confidence_threshold", 0.80)
            )
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

                image_path = screen_detector.capture("autoc_observation.png")
                if not image_path:
                    self.last_phase = "recover"
                    self.progress.error("Screenshot capture failed")
                    self.progress.maybe_report()
                    time.sleep(3)
                    continue

                observation = screen_detector.observe(image_path)
                self.last_observation = observation.to_dict()
                detected_targets = ui_detector.find(image_path)
                target_map = self._target_map(detected_targets)
                self.last_targets = [
                    {
                        "name": target.name,
                        "text": target.text,
                        "center": target.center,
                        "confidence": target.confidence,
                        "source": target.source,
                    }
                    for target in detected_targets
                ]

                state = self._state_from_observation(observation)
                decision = self.planner.choose(state)
                self.last_decision = {
                    "action": decision.action,
                    "reason": decision.reason,
                    "safe": decision.safe,
                }

                action = self.machine.plan_action(decision, target_map)
                self.last_phase = self.machine.state.phase.value

                print(
                    f"[Vision] village={observation.village} "
                    f"confidence={observation.confidence:.2f} "
                    f"resources={observation.resources}"
                )
                print(f"[Vision] dynamic_targets={len(detected_targets)}")
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
                    self.machine.after_action(
                        verified,
                        None if verified else "Android tap failed",
                    )
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
