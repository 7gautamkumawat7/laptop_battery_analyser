#!/usr/bin/env python3
"""
VoltPulse - Laptop Battery Health & Analytics Desktop Launcher
==============================================================
Launches the Flask backend server in a background thread and embeds
the interactive dashboard in a native PyWebView desktop window.
"""

import os
import socket
import sys
import threading
import time
import webview

# Import the Flask application instance
from app import app, get_or_create_report_data

HOST = "127.0.0.1"
PORT = 5000
DASHBOARD_URL = f"http://{HOST}:{PORT}"


def is_server_ready(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check if the local Flask TCP port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def start_flask_server():
    """Run Flask HTTP server in background thread."""
    try:
        get_or_create_report_data(force_generate=False)
    except Exception as e:
        print(f"[VoltPulse Backend] Warning during pre-warm: {e}")

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )


def main():
    """Main desktop application entry point."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print("[VoltPulse] Starting background Flask service...")
    server_thread = threading.Thread(target=start_flask_server, daemon=True)
    server_thread.start()

    # Wait until Flask socket is responsive (up to 5 seconds)
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if is_server_ready(HOST, PORT):
            break
        time.sleep(0.1)

    print(f"[VoltPulse] Launching native PyWebView UI at {DASHBOARD_URL} (1200x800)...")

    # Create native window (1200x800)
    window = webview.create_window(
        title="VoltPulse - Laptop Battery Health & Analytics",
        url=DASHBOARD_URL,
        width=1200,
        height=800,
        min_size=(900, 600),
        resizable=True,
        text_select=True,
        easy_drag=False
    )

    # Start PyWebView desktop GUI event loop (blocks until window is closed)
    webview.start(debug=False)
    print("[VoltPulse] Desktop window closed. Exiting application.")
    sys.exit(0)


if __name__ == "__main__":
    main()