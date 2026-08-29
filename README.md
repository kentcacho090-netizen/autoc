# AutoC

Smart automation foundation for a rooted Android/cloud-phone environment.

## Termux setup

```sh
pkg update -y
pkg install -y python git
cd ~
git clone https://github.com/kentcacho090-netizen/autoc.git
cd autoc
python -m pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:8765` in the cloud phone browser.

## Root

AutoC detects `su` automatically. If the cloud phone provides root, allow Termux/root access when prompted. If `su` is unavailable, the controller falls back to normal shell commands.

## Current architecture

- `ui.py` — local mobile control panel
- `bot_service.py` — start/stop runtime and settings reload
- `strategy.py` — smart decision layer
- `engine.py` — Android input/screenshot control
- `settings.json` — editable strategy configuration

The smart planner currently refuses to invent game state. A real screen/state detector is the next implementation layer; it should supply confirmed account information before the planner performs upgrade decisions.
