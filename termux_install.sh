#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "== AutoC Termux setup =="
pkg update -y
pkg install -y python git tesseract
python -m pip install --upgrade pip
pip install -r requirements.txt

mkdir -p "$HOME/.autoc"
echo
echo "Setup complete."
echo "Run: python main.py"
echo "Then open http://127.0.0.1:8765 in the cloud phone browser."
