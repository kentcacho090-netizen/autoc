#!/data/data/com.termux/files/usr/bin/bash
set -e

REPO="https://github.com/kentcacho090-netizen/autoc.git"
BRANCH="smart-automation-foundation"
DIR="$HOME/autoc"
BIN="$HOME/.local/bin"

printf '\n🤖 AutoC Termux installer\n\n'

# Avoid the interactive dpkg maintainer-file prompt that interrupted the first install.
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get -y -o Dpkg::Options::="--force-confold" upgrade
apt-get -y -o Dpkg::Options::="--force-confold" install git python python-pillow tesseract

if [ -d "$DIR/.git" ]; then
  echo "→ Updating existing AutoC checkout"
  cd "$DIR"
  git fetch origin
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  echo "→ Cloning AutoC"
  git clone -b "$BRANCH" "$REPO" "$DIR"
  cd "$DIR"
fi

# This project intentionally has no pip-native OpenCV dependency on Termux.
# OCR is supplied by the native tesseract package.
if [ -d .venv ]; then
  rm -rf .venv
fi
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

mkdir -p "$BIN"
cat > "$BIN/autoc" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$DIR"
source .venv/bin/activate
exec python main.py
EOF
chmod +x "$BIN/autoc"

# Make the launcher available in the current shell and future Termux sessions.
case ":$PATH:" in
  *":$BIN:"*) ;;
  *) export PATH="$BIN:$PATH" ;;
esac

if ! grep -qs 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
fi

ROOT_STATUS="not available"
if command -v su >/dev/null 2>&1; then
  if su -c id 2>/dev/null | grep -q 'uid=0'; then
    ROOT_STATUS="root available"
  else
    ROOT_STATUS="su found, root permission not granted"
  fi
fi

printf '\n✅ AutoC installation complete\n'
printf '📁 Directory: %s\n' "$DIR"
printf '🔐 Android access: %s\n' "$ROOT_STATUS"
printf '\nStart the terminal UI with:\n  autoc\n\nNo browser or web server is required.\n\n'
