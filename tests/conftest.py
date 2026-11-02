"""Settings for every test: no API key and no internet.

The tests must pass on a machine without the Claude API key and must never call
the real API or any real website (they would cost money, be slow and fail when a
site is down). So, for every test:

- ANTHROPIC_API_KEY (and the SDK's other key variables) are removed from the
  environment, even if a local .env loaded them earlier;
- opening a network connection to anything other than this machine (127.0.0.1,
  ::1) fails at once with NetworkBlocked. Tests that need a server start one on
  127.0.0.1 (see test_fetch.py).

This is what lets GitHub Actions run the whole suite on every pull request with
no secrets at all (.github/workflows/tests.yml).
"""

import ipaddress
import socket

import pytest

KEY_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "AISSTREAM_API_KEY", "KNMI_API_KEY")


class NetworkBlocked(RuntimeError):
    """A test tried to reach the internet."""


def _is_local(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return True  # Unix sockets and the like: never the internet
    host = address[0]
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a host name: would need the internet to resolve


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _guarded_connect(self, address):
    if not _is_local(address):
        raise NetworkBlocked(f"tests may not use the network (tried to connect to {address!r})")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if not _is_local(address):
        raise NetworkBlocked(f"tests may not use the network (tried to connect to {address!r})")
    return _real_connect_ex(self, address)


@pytest.fixture(autouse=True)
def no_keys_no_network(monkeypatch):
    for name in KEY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
