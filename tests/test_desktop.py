import socket
import threading

import pytest
from werkzeug.serving import make_server

import desktop
from app import create_app


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def busy_port():
    """A port held by some other program."""
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        yield other.getsockname()[1]


@pytest.fixture
def running_app():
    """A copy of the claim form already serving on a port."""
    server = make_server("127.0.0.1", 0, create_app(), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.port
    server.shutdown()
    server.server_close()


def test_port_states(busy_port, running_app):
    assert desktop.port_state(_free_port()) == "free"
    assert desktop.port_state(busy_port) == "busy"
    assert desktop.port_state(running_app) == "ours"


def test_choose_port_skips_ports_other_programs_use(busy_port):
    free = _free_port()
    assert desktop.choose_port([busy_port, free]) == (free, False)


def test_choose_port_reuses_a_running_copy(busy_port, running_app):
    assert desktop.choose_port([_free_port(), busy_port, running_app]) == (running_app, True)


def test_choose_port_falls_back_to_any_port(busy_port):
    assert desktop.choose_port([busy_port]) == (0, False)
