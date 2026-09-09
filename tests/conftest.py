


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


from conftest import NetworkUsedInATest


def _is_local(address) -> bool:
    """A loopback or UNIX socket, which is not the thing this guards against.

    Blocking these too would break a future local test server, and a
    debugger attaching over a socket — neither of which sends traffic to a
    school district.
    """
    if not isinstance(address, tuple) or not address:
        return True                       # a UNIX socket path
    host = str(address[0])
    return host in ("localhost", "::1") or host.startswith("127.")


@_pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    """Refuse every outbound connection unless the test asks for one.

    `@pytest.mark.network` opts a test back in — `tests/test_sced_doc.py`
    uses it deliberately, and a test that needs it should say so in its own
    file.

    **Both `connect` and `connect_ex`.** The first version patched only
    `connect`, and `connect_ex` is a different method on the same object
    that opens the same socket — so anything using it walked straight past
    the guard.

    This is a fixture, so it is inactive during import and collection. A
    module fetching at import time would bypass it; nothing here does, and a
    module that did would be the wrong shape anyway.
    """
    if request.node.get_closest_marker("network"):
        return

    def refuse(self, address):
        if _is_local(address):
            return _connect(self, address)
        raise NetworkUsedInATest(
            f"a test tried to connect to {address}. Stub the module's fetch "
            f"— these probes read school-district and government hosts, and "
            f"a test suite is not a reason to send them traffic. If the test "
            f"genuinely needs the network, mark it @pytest.mark.network.")

    def refuse_ex(self, address):
        if _is_local(address):
            return _connect_ex(self, address)
        refuse(self, address)

    _connect = _socket.socket.connect
    _connect_ex = _socket.socket.connect_ex
    monkeypatch.setattr(_socket.socket, "connect", refuse)
    monkeypatch.setattr(_socket.socket, "connect_ex", refuse_ex)
