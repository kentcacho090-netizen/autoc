# AUTO — Android test/run

## 1. Enter the project

```sh
cd ~/autoc
```

## 2. Install Python dependency

```sh
python -m pip install -r requirements.txt
```

## 3. Verify the installation

```sh
python self_test.py
```

`adb` and `tesseract` are external Android/Termux programs. The self-test
warns if either is missing instead of crashing.

## 4. Verify ADB

```sh
adb devices
```

There must be one device with state `device`.

## 5. Run one safe observation

Make sure Clash of Clans is open, then:

```sh
python main.py --once
```

This launches the game, captures `autoc_observation.png`, and reads the HUD.
It does **not** blindly tap buttons or start an attack.

## 6. Continuous observation

```sh
python main.py --loop
```

Stop with `Ctrl+C`.

## Important

The old program contained example coordinates for a different screen size and
blindly tapped them. Those coordinates have been removed from the active loop.
Do not reintroduce guessed coordinates. The next action layer must first detect
the relevant CoC screen/state and then act on that state.
