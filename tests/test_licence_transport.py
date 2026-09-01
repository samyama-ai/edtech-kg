"""`page_text` — how a page is FETCHED, as opposed to what is read out of it.

Split from `tests/test_licence_positions.py` when that file passed the
500-line review limit. Split by SUBJECT: this file covers the transport — the
request it sends, the size it will accept, and the charset it decodes through.
That file covers the positions extracted from a page once it has arrived.

The charset cases are the bulk of it because they are where this has gone
wrong twice: a guard written for `LookupError` alone missed the two names that
raise `UnicodeError`, and a comment claiming all three raise missed the one
that does not raise at all and decodes to nonsense instead.
"""

from __future__ import annotations

import pytest

from etl import licence_positions as lp


def test_a_page_that_does_not_answer_raises_unreachable(monkeypatch):
    """Two different facts, and only one is about the publisher.

    Reporting a timeout as `MalformedSource` invites the next reader to
    conclude the terms changed. `Unreachable` subclasses it, so every existing
    handler still catches it and the CLI keeps one exit code.
    """
    def refuse(*_a, **_k):
        raise OSError("connection reset")

    monkeypatch.setattr(lp.urllib.request, "urlopen", refuse)
    with pytest.raises(lp.Unreachable, match="did not answer"):
        lp.page_text("https://example.invalid/terms")
    # And it is still a MalformedSource, or `main` stops catching it.
    assert issubclass(lp.Unreachable, lp.MalformedSource)


def test_the_response_charset_is_honoured_not_assumed(monkeypatch):
    """These are three third-party pages quoted VERBATIM as licence positions.

    A publisher serving Latin-1 would have turned every accented character in
    a quoted sentence into a replacement character, silently.
    """
    # No em dash: it has no Latin-1 encoding, and the fixture must be a page
    # a publisher could actually serve.
    body = "Café Frais licence".encode("latin-1")

    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "latin-1")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return body

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    read = lp.page_text("https://example.test/x")
    assert "Café Frais" in read
    # Decoded as UTF-8 the accented byte is a replacement character, so this
    # fails loudly if the charset is ignored rather than passing on a
    # substring that happens to survive.
    assert "\ufffd" not in read


def test_an_unknown_charset_falls_back_rather_than_raising(monkeypatch):
    """A codec name Python does not know must not become a traceback."""
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "not-a-real-codec")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        # NOT pure ASCII. A body that decodes identically under utf-8 and
        # latin-1 cannot tell them apart, so an assertion over it passes
        # whichever codec the fallback actually used — and switching the
        # fallback to latin-1 left the suite green. `caf\xc3\xa9` is "café"
        # under utf-8 and "cafÃ©" under latin-1.
        def read(self, amount=None): return "plain café text".encode("utf-8")

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    # The TEXT, which is what distinguishes the codecs.
    assert lp.page_text("https://example.test/x") == "plain café text"


def test_the_request_identifies_this_project_and_bounds_the_wait(monkeypatch):
    """The header three publishers see when this repo reaches them.

    `USER_AGENT` is how O*NET, the Urban Institute and Credential Engine
    identify this traffic — the same courtesy the state-department probe found
    was not enough on its own, and the reason the 403s there could be
    characterised at all. Neither it nor the timeout had an assertion.
    """
    seen = {}

    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return b"body"

    def capture(request, timeout=None):
        seen["agent"] = request.get_header("User-agent")
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(lp.urllib.request, "urlopen", capture)
    lp.page_text("https://example.test/terms")

    assert seen["agent"] == lp.USER_AGENT
    assert "edtech-kg" in seen["agent"] and "git.samyama.ai" in seen["agent"], (
        "the agent must name the project and where to complain about it")
    assert seen["timeout"], "an unbounded fetch can hang the probe forever"


@pytest.mark.parametrize("charset", ["idna", "undefined"])
def test_a_charset_python_refuses_falls_back_rather_than_raising(
        charset, monkeypatch, capsys):
    """`LookupError` alone did not cover these.

    `idna` and `undefined` are codecs Python knows and refuses for bytes,
    raising `UnicodeError` — so they escaped a guard written for an unknown
    name and reached the caller as a traceback.

    `punycode` is deliberately not here: it does not raise, it decodes to
    nonsense. That is a different problem and this guard is not the fix for
    it; a fixture using it would have tested nothing.
    """
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: charset)})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return b"plain text"

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert lp.page_text("https://example.test/x") == "plain text"
    # And it SAYS SO. The comment beside this fallback warned that falling
    # back silently is how a page gets quoted through the wrong codec and
    # nobody finds out — and then fell back silently. A claim about the code
    # that only the comment makes is a claim nothing keeps true.
    warned = capsys.readouterr().err
    assert charset in warned, (
        f"the fallback did not name the charset it could not use: {warned!r}")
    # NOT `"utf-8" in warned` — that was satisfied by the literal in the
    # message. Switching the actual fallback to latin-1 while the message went
    # on claiming utf-8 left the suite green. The codec is one constant used by
    # both, and what is asserted is the TEXT it produced.
    # NOT `lp.FALLBACK_CHARSET in warned` — the constant is in the message
    # too, so that compares a literal with itself. The decoded TEXT is what
    # distinguishes the codecs, and the punycode test below asserts on it.
    assert "utf-8" in warned


def test_a_charset_that_works_is_not_warned_about(monkeypatch, capsys):
    """The other direction. A warning on every page is a warning nobody
    reads, and these three pages are fetched on every recorded run."""
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return b"plain text"

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert lp.page_text("https://example.test/x") == "plain text"
    assert capsys.readouterr().err == ""


def test_an_enormous_body_is_refused_rather_than_read(monkeypatch):
    """`timeout` bounds a socket operation, not a transfer.

    A slow drip had no ceiling, and `flatten`'s script-strip is quadratic — so
    a body of unterminated `<script` tokens costs far more than its size. On
    three licence pages, anything past a few megabytes is not one of them.
    """
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None):
            return b"x" * (amount if amount else lp.MAX_PAGE + 1)

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(lp.MalformedSource, match="more than"):
        lp.page_text("https://example.test/x")


def test_a_body_within_the_cap_is_read_whole(monkeypatch):
    """The false-positive direction — the cap must not truncate a real page."""
    body = b"a" * (lp.MAX_PAGE // 2)

    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return body

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert len(lp.page_text("https://example.test/x")) == len(body)


def test_a_charset_that_decodes_to_nonsense_is_caught_too(monkeypatch, capsys):
    """`punycode` is the hole an `except` cannot see.

    `idna` and `undefined` raise. `punycode` DECODES — an ASCII licence page
    comes back as two characters of mojibake — so it walks past every
    exception handler and reaches the "quoted through the wrong codec"
    outcome the warning exists to prevent.

    Worse than silent: the refusal downstream said "what came back is not this
    page", which sends the next reader looking for a redirect or a changed
    licence when the cause is one response header.
    """
    # ASCII, deliberately. Given non-ASCII bytes `punycode` RAISES and takes
    # the other branch, so the decodes-to-nonsense path would never run — the
    # test would pass while checking something else entirely.
    body = b"This license applies only to downloadable files"

    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "punycode")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return body

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    # Decoded through the DECLARED codec this is two characters of mojibake;
    # the assertion is on the text, so it fails if the fallback stops running.
    assert lp.page_text("https://example.test/x") == body.decode("utf-8")
    warned = capsys.readouterr().err
    assert "punycode" in warned and "nonsense" in warned, warned


def test_an_empty_body_is_not_called_nonsense(monkeypatch, capsys):
    """A page with no bytes decodes to nothing under every codec. That is a
    different failure, and the size guard and the refusals downstream own it —
    reporting it as a charset problem would misdirect the same way."""
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return b""

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert lp.page_text("https://example.test/x") == ""
    assert capsys.readouterr().err == ""
