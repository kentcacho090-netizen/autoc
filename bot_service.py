import json
import threading
import time

from action_gate import SemanticActionGate
from engine import ADBController
from strategy import AccountState, SmartPlanner
from automation_state import SmartAutomationStateMachine, Target
from diagnostics import DiagnosticStore
from diagnostic_report import DiagnosticReporter
from progress import ProgressReporter
from selection_context import SelectionContextDetector
from ui_targets import UITargetDetector
from verified_actions import VerifiedActions
from vision import ScreenDetector


class BotService:
    """Long-running smart loop with dynamic perception and verified actions."""

    def __init__(self, settings_file):
        self.settings_file = settings_file
        self.running = False
        self._thread = None
        self.last_observation = None
        self.last_decision = None
        self.last_targets = []
        self.last_phase = "observe"
        self.progress = ProgressReporter(interval_seconds=60.0)
        self.diagnostics = DiagnosticStore()
        self.reporter = DiagnosticReporter()
        self.reload()

    def reload(self):
        with open(self.settings_file, "r", encoding="utf-8") as handle:
            self.settings = json.load(handle)
        vision_settings = self.settings.get("vision", {})
        threshold = float(vision_settings.get("confidence_threshold", 0.70))
        progress_interval = max(
            1.0,
            float(vision_settings.get("progress_interval_seconds", 60)),
        )
        self.planner = SmartPlanner(self.settings.get("strategy", "balanced"), threshold)
        self.machine = SmartAutomationStateMachine(
            min_target_confidence=max(
                0.80,
                float(vision_settings.get("target_confidence_threshold", threshold)),
            ),
            max_failures=int(vision_settings.get("max_action_failures", 3)),
        )
        self.action_gate = SemanticActionGate(
            min_context_confidence=max(
                0.85,
                float(vision_settings.get("context_confidence_threshold", 0.85)),
            )
        )
        self.context_detector = SelectionContextDetector()
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
            town_hall=getattr(observation, "town_hall", None),
            builder_base_unlocked=getattr(observation, "builder_base_unlocked", False),
            gold=resources.get("gold"),
            elixir=resources.get("elixir"),
            dark_elixir=resources.get("dark_elixir"),
            confidence=observation.confidence,
        )

    @staticmethod
    def _target_map(detected_targets):
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

    @staticmethod
    def _semantic_evidence(action, action_target, ui_detector):
        """Collect fresh semantic labels without treating Upgrade as an object label."""
        evidence = []
        if action_target is not None:
            evidence.append(action_target.text)
        accessibility = getattr(ui_detector, "accessibility", None)
        if accessibility is not None:
            try:
                nodes = accessibility.dump()
            except Exception:
                nodes = []
            for node in nodes:
                text = node.searchable_text
                if text:
                    evidence.append(text)
        return evidence

    def _write_diagnostics(self, error=None):
        return self.diagnostics.write(
            observation=self.last_observation,
            decision=self.last_decision,
            progress=self.progress.snapshot.as_dict(),
            targets=self.last_targets,
            phase=self.last_phase,
            error=error,
        )

    def _write_report(self):
        try:
            return self.reporter.write()
        except OSError as exc:
            print(f"[Diagnostics] Report write failed: {exc}")
            return None

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
        verified_actions = VerifiedActions(controller, ui_detector)

        while self.running:
            self.progress.cycle_started("observe")
            try:
                if not controller.check_connection():
                    self.last_phase = "recover"
                    self.progress.error("Android control unavailable")
                    self._write_diagnostics("Android control unavailable")
                    self._write_report()
                    self.progress.maybe_report()
                    time.sleep(5)
                    continue

                image_path = screen_detector.capture("autoc_observation.png")
                if not image_path:
                    self.last_phase = "recover"
                    self.progress.error("Screenshot capture failed")
                    self._write_diagnostics("Screenshot capture failed")
                    self._write_report()
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
                else:
                    evidence = self._semantic_evidence(action.name, action.target, ui_detector)
                    context = self.context_detector.identify(
                        action_name=action.name,
                        target=action.target,
                        evidence=evidence,
                        village=getattr(observation, "village", "unknown"),
                        confidence=getattr(observation, "confidence", 0.0),
                        source="accessibility+ocr",
                    )
                    if not self.action_gate.authorize(action, action.target, context):
                        self.progress.action_refused(
                            f"Semantic context did not authorize {action.name}"
                        )
                        print("[ActionGate] Refused: target lacks sufficient semantic context")
                    elif self.machine.before_action(action):
                        result = verified_actions.tap_named(action.name)
                        self.machine.after_action(result.ok, None if result.ok else result.reason)
                        self.last_phase = self.machine.state.phase.value
                        if result.ok:
                            self.progress.action_succeeded(action.name)
                        else:
                            self.progress.error(result.reason or "Verified action failed")
                    else:
                        self.progress.action_refused(action.reason or "Action gate refused target")

                self.progress.maybe_report()
                self._write_diagnostics()
                self._write_report()
                delay = max(1, int(self.settings.get("timing", {}).get("cycle_delay", 10)))
                time.sleep(delay)
            except Exception as exc:
                self.machine.after_action(False, str(exc))
                self.last_phase = self.machine.state.phase.value
                self.progress.error(str(exc))
                self._write_diagnostics(str(exc))
                self._write_report()
                self.progress.maybe_report()
                print(f"[Bot] Recovered from cycle error: {exc}")
                time.sleep(2)

        self.progress.maybe_report(force=True)
        self._write_diagnostics()
        self._write_report()
