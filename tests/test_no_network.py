"""The backstop that keeps this suite off other people's servers.

`tests/conftest.py` refuses a socket to every test that does not carry
`@pytest.mark.network`. **A guard nothing tests is a guard nobody knows is
broken** — this file is why the guard is not one of those.

It caught a real case on its first run: `tests/test_sced_doc.py`'s
live-source check, which had been making real requests on every full-suite
run and is now marked.
"""

from __future__ import annotations

import socket

import pytest

from conftest import NetworkUsedInATest


def test_an_outbound_connection_is_refused():
    """The thing the guard exists for."""
    with pytest.raises(NetworkUsedInATest, match="school-district"):
        socket.socket().connect(("example.com", 80))


def test_connect_ex_is_refused_too():
    """**`connect_ex` is a different method that opens the same socket.**
    The first version patched only `connect`, so anything using it walked
    straight past the guard — and `connect_ex` is what a library reaching for
    a non-raising connect will call."""
    with pytest.raises(NetworkUsedInATest):
        socket.socket().connect_ex(("example.com", 80))


def test_loopback_is_allowed():
    """Blocking these would break a future local test server and a debugger
    attaching over a socket — neither of which sends traffic anywhere."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        client = socket.socket()
        client.connect(listener.getsockname())     # must not raise
        client.close()
    finally:
        listener.close()


@pytest.mark.network
def test_the_marker_opts_a_test_back_in():
    """The escape hatch, exercised — otherwise a marked test would be
    refused and nobody would find out until they wrote one.

    It resolves a name rather than fetching, so it proves the guard is off
    without adding traffic of its own.
    """
    with pytest.raises((socket.gaierror, OSError)):
        socket.socket().connect(("this-host-does-not-exist.invalid", 80))
