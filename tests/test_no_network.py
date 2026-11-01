"""The guard in conftest.py: tests run without API keys and cannot reach the internet."""

import os
import socket

import pytest

from conftest import KEY_VARIABLES, NetworkBlocked


def test_no_api_key_is_visible_to_tests():
    for name in KEY_VARIABLES:
        assert name not in os.environ


def test_internet_connections_are_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(NetworkBlocked):
            s.connect(("93.184.216.34", 443))  # any public address


def test_the_claude_api_cannot_be_reached():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(NetworkBlocked):
            s.connect(("api.anthropic.com", 443))


def test_this_machine_is_still_allowed():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.create_connection(server.getsockname(), timeout=5):
            pass
