#!/data/data/com.termux/files/usr/bin/bash
set -e

REPO="https://github.com/kentcacho090-netizen/autoc.git"
BRANCH="smart-automation-foundation"
DIR="$HOME/autoc"

printf '\n🤖 AutoC Termux installer\n\n'

pkg update -y
pkg upgrade -y
pkg install -y git python clang make pkg-config libjpeg-turbo libpng

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

if [ ! -d .venv ]; then
  python -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/autoc" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$DIR"
source .venv/bin/activate
exec python main.py
EOF
chmod +x "$HOME/.local/bin/autoc"

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
printf '\nStart AutoC with:\n  autoc\n\nThen open:\n  http://127.0.0.1:8765\n\nNote: this installs the automation framework and local UI. It does not bypass game anti-cheat or enforcement systems.\n'
