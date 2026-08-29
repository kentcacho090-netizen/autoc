"""AutoC entry point.

Run this inside Termux on the Android/cloud phone, then open the local UI.
"""
from ui import app


if __name__ == "__main__":
    print("🤖 AutoC starting on http://127.0.0.1:8765")
    app.run(host="127.0.0.1", port=8765, debug=False)
