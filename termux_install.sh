#!/data/data/com.termux/files/usr/bin/bash
set -e

REPO="https://github.com/kentcacho090-netizen/autoc.git"
BRANCH="smart-automation-foundation"
DIR="$HOME/autoc"
BIN="$PREFIX/bin"

printf '\n🤖 AutoC Termux installer\n\n'

# Do not run a full upgrade here. This avoids the interactive maintainer-file
# prompt that interrupted the previous fresh installation.
export DEBIAN_FRONTEND=noninteractive
pkg update -y
apt-get -y -o Dpkg::Options::="--force-confold" install git python python-pillow tesseract

if [ -d "$DIR/.git" ]; then
  echo "→ Updating existing AutoC checkout"
  cd "$DIR"
  git fetch origin
  git checkout "$BRANCH"
  git reset --hard "origin/$BRANCH"
else
  echo "→ Cloning AutoC"
  git clone -b "$BRANCH" "$REPO" "$DIR"
  cd "$DIR"
fi

# AutoC is intentionally dependency-light on Termux. Pillow is supplied by
# the Termux package manager and OCR is supplied by native tesseract.
rm -rf .venv 2>/dev/null || true

mkdir -p "$BIN"
cat > "$BIN/autoc" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$DIR"
exec python main.py
EOF
chmod +x "$BIN/autoc"

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
printf '\nStart the terminal UI with:\n  autoc\n\nNo browser or web server is required.\n'
