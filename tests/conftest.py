


# --------------------------------------------------------------------------
# NO TEST MAY OPEN A SOCKET.
#
# Every probe test in this tree stubs its own fetch, and they all do it
# correctly today. The exposure is the NEXT one — or a refactor that adds a
# fetch path the stubs do not cover. `course_paths` reaching a real sitemap
# from CI is five requests to a school district on every push, and it would
# pass.
#
# A probe's politeness is only as good as the guarantee that its tests do not
# use the network at all. This is that guarantee, made structural rather than
# left to each author.
#
# It patches the CONNECT, not the library, so it holds however the request is
# made — urllib, requests, a raw socket.
import socket as _socket

import pytest as _pytest


class NetworkUsedInATest(RuntimeError):
    """A test tried to open a socket. Stub the fetch instead."""


@_pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    """Refuse every outbound connection unless the test asks for one.

    `@pytest.mark.network` opts a test back in — nothing uses it today, and
    a test that needs it should say so in its own file.
    """
    if request.node.get_closest_marker("network"):
        return

    def refuse(self, address):
        raise NetworkUsedInATest(
            f"a test tried to connect to {address}. Stub the module's fetch "
            f"— these probes read school-district and government hosts, and "
            f"a test suite is not a reason to send them traffic.")

    monkeypatch.setattr(_socket.socket, "connect", refuse)
