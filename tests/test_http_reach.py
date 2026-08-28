"""Whether a source answers, and what its silence is allowed to mean.

Split out of `tests/test_probe_apprenticeship.py` when it passed the 500-line
review limit. Everything here drives `reachable`, `resolves_anywhere` and
`attempt`; the crosswalk parsing and the route arithmetic stay next door.

The subject is one distinction. A name that resolves NOWHERE is broken at the
publisher's end and can be asserted. A name that resolves and then will not
answer cannot be told apart, from one network, from an outbound restriction —
so `docs/sources/careeronestop.md` asserts the first and declines the second,
and every test here exists to keep that line where it is.
"""

from __future__ import annotations

import subprocess

import pytest

from etl import http_reach as probe


def test_a_host_that_does_not_resolve_is_told_apart_from_one_that_refuses(monkeypatch):
    """The distinction the CareerOneStop page turns on, and the reason it can
    assert one finding and not the other.

    A name that resolves nowhere is broken at the publisher's end. A resolved
    address that refuses a connection cannot be told apart, from one network,
    from an outbound restriction. Reporting both as "unreachable" would let the
    page overclaim.
    """
    def resolve(host):
        if host == "gone.example":
            raise OSError(8, "nodename nor servname provided")
        return "10.0.0.1"
    monkeypatch.setattr(probe.socket, "gethostbyname", resolve)

    # `dig` too. This patched `gethostbyname` only, so `resolves_anywhere`
    # shelled out to the real `dig @8.8.8.8` for every host in REACH — real
    # network calls from a unit test, answering about the internet rather
    # than about the fixture.
    def dug(argv, *a, **k):
        host = argv[-1]
        answer = "" if host == "gone.example" else "10.0.0.1\n"
        return subprocess.CompletedProcess(argv, 0, stdout=answer, stderr="")
    monkeypatch.setattr(probe.subprocess, "run", dug)

    def refuse(*a, **k):
        raise probe.urllib.error.URLError("timed out")
    monkeypatch.setattr(probe.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(probe, "REACH", [("gone", "https://gone.example/"),
                                         ("refusing", "https://refusing.example/")])

    by_name = {row["source"]: row for row in probe.reachable()}
    assert "does not resolve" in by_name["gone"]["status"]
    assert by_name["gone"]["dns"] is None
    assert "no connection" in by_name["refusing"]["status"], (
        "a refused connection is reported as a DNS failure — a claim the "
        "careeronestop page explicitly declines to make")
    assert by_name["refusing"]["dns"] == "10.0.0.1"


def test_a_name_that_resolves_nowhere_is_told_apart_from_one_this_network_cannot_see(monkeypatch):
    """The distinction both pages rest on, and it needs more than one resolver.

    `socket.gethostbyname()` alone answers "this network cannot resolve it".
    The page claims "no A record from ANY resolver", which is a claim about the
    publisher — so the probe asks the public resolvers too, and only makes the
    strong claim when every resolver it could ask said no.
    """
    monkeypatch.setattr(probe.socket, "gethostbyname",
                        lambda host: (_ for _ in ()).throw(OSError(8, "no")))

    # `probe.subprocess` is patched, so no real `dig @8.8.8.8` leaves the
    # machine. Without this the test queried Google's resolver for real — a
    # network call from a suite that is supposed to be hermetic, and an
    # assertion whose answer depended on someone else's DNS.
    asked = []

    def answer(cmd, **kw):
        asked.append(cmd)

        class Out:
            returncode = 0
            stdout = "" if any("gone.example" in c for c in cmd) else "10.0.0.1\n"
        return Out()
    monkeypatch.setattr(probe.subprocess, "run", answer)

    gone = probe.resolves_anywhere("gone.example")
    assert asked, "the public resolvers were never asked"
    assert all(cmd[0] == "dig" for cmd in asked), asked
    assert gone["resolves_nowhere"] is True
    assert set(gone["by_resolver"]) == {"system", "Google", "Cloudflare"}

    assert gone["by_resolver"] == {"system": None, "Google": None, "Cloudflare": None}, (
        f"the strong claim was made from something other than three negative "
        f"answers: {gone['by_resolver']}")

    local = probe.resolves_anywhere("fine.example")
    assert local["by_resolver"]["Google"] == "10.0.0.1"
    assert local["resolves_nowhere"] is False, (
        "a name the public resolvers DO know was reported as resolving "
        "nowhere — that is a claim about the publisher made from a local "
        "failure")


def test_a_resolver_that_cannot_be_asked_is_not_counted_as_a_no(monkeypatch):
    """"We could not ask" is not "there is no record". A machine without `dig`,
    or one that cannot reach 8.8.8.8, must not turn into evidence about a
    publisher."""
    monkeypatch.setattr(probe.socket, "gethostbyname",
                        lambda host: (_ for _ in ()).throw(OSError(8, "no")))

    def missing(cmd, **kw):
        raise FileNotFoundError("dig")
    monkeypatch.setattr(probe.subprocess, "run", missing)

    got = probe.resolves_anywhere("gone.example")
    assert got["by_resolver"]["Google"] == "unknown"
    assert got["resolves_nowhere"] is False, (
        "an unreachable resolver was read as a negative answer")


def test_the_anonymous_request_really_sends_no_user_agent(monkeypatch):
    """`urllib` inserts `Python-urllib/3.x` unless the header is cleared, so an
    "anonymous" arm measures a DEFAULT agent rather than an absent one — the
    trap edtech-kg#37 recorded on bls.gov, where the whole finding turned on
    which agent was sent.

    Both pages separate a block on anonymity from a block on automation, and
    that separation is only as good as this.
    """
    sent = []

    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def capture(request, *a, **k):
        sent.append(request.get_header("User-agent"))
        return R()
    monkeypatch.setattr(probe.urllib.request, "urlopen", capture)

    probe.attempt("https://x.example/", probe.USER_AGENT)
    probe.attempt("https://x.example/", None)
    assert sent[0] == probe.USER_AGENT
    assert sent[1] == "", (
        f"the anonymous request sent {sent[1]!r} — urllib's default agent, "
        f"not an absent one")


def test_a_cname_or_a_message_from_dig_is_not_taken_as_an_address(monkeypatch):
    """`found[0]` took the first line that was not a name.

    `dig +short` prints a CNAME chain before the address, and on some failures
    prints a message instead. Whatever that first line said became the answer
    a resolver gave — and it appears on the page as the address the host
    resolves to, which is a measured claim.
    """
    def dug(argv, *a, **k):
        host = argv[-1]
        if host == "chained.example":
            out = "alias.cdn.example.\n93.184.216.34\n"
        elif host == "broken.example":
            out = ";; connection timed out; no servers could be reached\n"
        else:
            out = "10.0.0.1\n"
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
    monkeypatch.setattr(probe.subprocess, "run", dug)
    monkeypatch.setattr(probe.socket, "gethostbyname", lambda h: "10.0.0.1")

    chained = probe.resolves_anywhere("chained.example")
    assert chained["by_resolver"]["Google"] == "93.184.216.34", (
        "a CNAME was reported as the resolved address")

    broken = probe.resolves_anywhere("broken.example")
    assert broken["by_resolver"]["Google"] is None, (
        "a dig error message was reported as an address")


def test_a_405_is_labelled_as_being_about_the_method(monkeypatch):
    """A bare "405" sits in the table beside 403 and 404 and reads as a
    property of the publisher. It says only that HEAD is not allowed."""
    def refuse(*a, **k):
        raise probe.urllib.error.HTTPError("u", 405, "Method Not Allowed", {}, None)
    monkeypatch.setattr(probe.urllib.request, "urlopen", refuse)

    status = probe.attempt("https://example.invalid/", probe.USER_AGENT)
    assert status.startswith("405") and "GET" in status, (
        f"a 405 is reported as {status!r}, which reads as a block on this "
        f"source rather than on the method")


def test_a_resolver_that_could_not_be_asked_is_not_read_as_one_that_answered():
    """Three states, and two of them shared a message.

    "the system resolver failed" splits into *a public resolver answered, so
    this is local* and *no public resolver could be ASKED, so we know
    nothing* — and both produced the first sentence. On a machine with no
    `dig`, or no route to 8.8.8.8, the page would claim another resolver
    answered when none was reached, which is a statement about the publisher
    made from a broken network.
    """
    def boom(*a, **k):
        raise OSError(51, "Network is unreachable")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(probe.socket, "gethostbyname", boom)
        mp.setattr(probe.subprocess, "run", boom)
        mp.setattr(probe.urllib.request, "urlopen", boom)
        mp.setattr(probe, "REACH", [("x", "https://x.example/")])

        status = probe.reachable()[0]["status"]

    assert "no public resolver could be asked" in status, (
        f"with nothing reachable the status was {status!r}, which claims "
        f"another resolver answered when none was")
    assert "publisher" in status, "it does not say what the measurement is of"


def test_a_hex_ish_token_from_dig_is_not_taken_as_an_address():
    """`[0-9a-fA-F:]{3,}` also matches `deadbeef` and `abc`.

    Whatever it matched went onto the page as the address a resolver
    returned, which is a measured claim.
    """
    for text in ("8.8.8.8", "2001:4860:4860::8888"):
        assert probe.is_address(text), f"{text} is an address"
    for text in ("deadbeef", "abc", "www.example.com.", "; timed out", "cafe"):
        assert not probe.is_address(text), (
            f"{text!r} would be reported as the address a resolver returned")


def test_the_control_hosts_the_pages_cite_are_in_the_run():
    """`REACH`'s contents were unpinned.

    Both reach tests monkeypatch it away, and a doc test checks the page NAMES
    the control hosts — so dropping `careertech.org` from the run leaves both
    green while the page keeps citing a host nothing reached. The controls are
    what make "this is not a general egress failure" an argument rather than an
    assertion, so they are pinned to the list the run actually walks.
    """
    urls = " ".join(url for _, url in probe.REACH if url)
    for host in ("onetcenter.org", "nces.ed.gov", "careertech.org"):
        assert host in urls, (
            f"{host} is cited on both pages as a control reached in the same "
            f"session, and is not in REACH — so the claim is unbacked")

    for host in ("careeronestop.org", "apprenticeship.gov", "data.gov"):
        assert host in urls, f"{host} is a source both pages report on"
