#!/usr/bin/env python3
"""AI Multi-Model Chat Panel - Flask server for serving static files."""

import os
import sys
from pathlib import Path

from flask import Flask, send_from_directory

app = Flask(__name__)
STATIC_DIR = Path(__file__).parent / "static"


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)


if __name__ == "__main__":
    os.makedirs(STATIC_DIR, exist_ok=True)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8082
    print(f"AI Chat Panel running on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
