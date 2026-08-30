#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python -m compileall -q .
python verify_repo.py
