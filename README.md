# AutoC

Smart automation foundation for a rooted Android/cloud-phone Termux environment.

## Termux setup

```sh
pkg update -y
pkg install -y python git tesseract
cd ~
git clone --single-branch https://github.com/kentcacho090-netizen/autoc.git autoc
cd autoc
python main.py
```

The default `main` branch is the canonical runnable branch. `smart-automation-foundation` remains available for development history.

AutoC uses Android shell input and screenshots through the local Termux/root environment. No browser dashboard is required.

## Root / Android control

AutoC detects `su` automatically. If the cloud phone provides root, allow Termux/root access when prompted. If `su` is unavailable, the controller falls back to the normal shell.

## Current architecture

- `main.py` — Termux entry point
- `tui.py` — interactive terminal interface
- `bot_service.py` — long-running observation/planning loop and one-minute progress reporting
- `strategy.py` — smart decision layer
- `automation_state.py` — action safety gate and recovery state machine
- `vision.py` — screenshot/resource OCR
- `resource_observer.py` — resource normalization and observation helpers
- `ui_targets.py` — verified OCR UI-target discovery
- `verified_actions.py` — observe-before/after action helper
- `townhall.py` — adaptive Town Hall panel probe
- `engine.py` — Android launch, screenshot, tap and swipe control
- `settings.json` — runtime strategy and timing configuration
- `detector_config.json` — vision calibration

## Safety model

The planner decides action categories rather than raw coordinates. The action state machine refuses an action when a verified target is not available or confidence is below the configured threshold. This prevents the old fixed-coordinate failure mode.

Optional resources are allowed to be unavailable on lower Town Hall accounts. Town Hall level and feature availability are treated as separate observations rather than assuming that every account has Dark Elixir or Builder Base available.

## Verification

Before enabling any automation, run:

```sh
bash run_verify.sh
```

The repository CI also compiles the Python modules, validates JSON, imports the application modules, and runs the deterministic test suite.
