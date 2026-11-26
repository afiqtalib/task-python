"""Desktop launcher: runs the claim form on this PC and opens it in the browser.

This is what the installed app (ClaimForm.exe) runs; ``python desktop.py`` does
the same from source. Closing the console window stops the app.

It always tries the same ports, in the same order, so the browser keeps the
saved draft between launches (a draft belongs to one address). Starting it a
second time just opens the browser on the copy that is already running.
"""
from __future__ import annotations

import json
import logging
import socket
import sys
import traceback
import urllib.request
import webbrowser
from typing import Iterable

from werkzeug.serving import make_server

from claim_form import config

TITLE = "DBT Claim Form"
HOST = "127.0.0.1"
PORTS = range(5055, 5065)

# Never send the localhost check through a system / corporate proxy.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def port_state(port: int, host: str = HOST) -> str:
    """``"free"``, ``"ours"`` (this app is already running there) or ``"busy"``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: fail if anyone holds the port
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind((host, port))
            return "free"
        except OSError:
            pass
    try:
        with _opener.open(f"http://{host}:{port}/api/ping", timeout=1) as res:
            return "ours" if json.load(res).get("app") == config.APP_ID else "busy"
    except (OSError, ValueError):
        return "busy"


def choose_port(ports: Iterable[int] = PORTS) -> tuple[int, bool]:
    """``(port, already_running)``. A running copy wins over a free port.

    Port 0 (Windows picks one) is the last resort when every port is taken.
    """
    first_free = None
    for port in ports:
        state = port_state(port)
        if state == "ours":
            return port, True
        if state == "free" and first_free is None:
            first_free = port
    return (first_free, False) if first_free is not None else (0, False)


def _set_console_title(title: str) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(title)


def main() -> None:
    _set_console_title(TITLE)
    port, running = choose_port()
    if running:
        url = f"http://{HOST}:{port}/"
        print(f"{TITLE} is already running - opening {url}")
        webbrowser.open(url)
        return

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # no line per request

    from app import app

    server = make_server(HOST, port, app, threaded=True)
    url = f"http://{HOST}:{server.port}/"
    print(f"\n  {TITLE} is running at {url}\n")
    print("  Your browser opens by itself. Keep this window open while you use the form;")
    print("  close it to stop the app.\n")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        if getattr(sys, "frozen", False):  # keep the window open so the error can be read
            input(f"\n{TITLE} could not start. Press Enter to close this window.")
        sys.exit(1)
