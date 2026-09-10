"""The competitor probe, driven without the network.

edtech-kg#47. The measurement is term counts over public pages, and the two
things that can go wrong are both about permission rather than counting: a
page fetched before its robots.txt was read, and a page fetched because a
parser said yes when the publisher plainly meant no.

`tests/conftest.py` does not exist in this repo, so nothing here relies on a
suite-wide socket guard: every fetch is monkeypatched, and the last test runs
this file under a watcher to prove it.
"""

from __future__ import annotations


from etl import probe_competitors as probe


def test_the_robots_gate_is_inside_fetch(monkeypatch):
    """**The gate is code, not a habit.** On #41 the ECS table was fetched
    several times BEFORE its robots.txt was read — the wrong order, and the
    reason this check lives inside `fetch` where a caller cannot skip it.
    """
    reached = []
    monkeypatch.setattr(probe, "robots_for",
                        lambda url: {"allowed": False, "robots_status": 200})
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: reached.append(1))
    found = probe.fetch("https://blocked.test/")
    assert found["fetched"] is False
    assert not reached, "a disallowed page was fetched anyway"


def test_a_refusal_is_recorded_rather_than_raised(monkeypatch):
    """A vendor that will not answer an identified research agent is a fact
    about the vendor, not an error in the probe."""
    import io
    import urllib.error

    monkeypatch.setattr(probe, "robots_for", lambda url: {"allowed": True})

    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 403, "no", {},
                                     io.BytesIO(b""))

    monkeypatch.setattr(probe.urllib.request, "urlopen", refuse)
    found = probe.fetch("https://refuses.test/")
    assert found["status"] == 403 and found["fetched"] is False


def test_coursicle_is_excluded_and_not_in_the_fetch_list():
    """**The judgement this issue turned on.** Its robots.txt disallows a
    list of AI user-agents; ours is not on it, so a parser permits the fetch.

    Being excluded has to mean it is not in `VENDORS` at all — an exclusion
    that lives only in a comment is one somebody adds back.
    """
    assert "Coursicle" in probe.EXCLUDED
    assert "Coursicle" not in probe.VENDORS
    for name in probe.EXCLUDED:
        assert name not in probe.VENDORS, f"{name} is excluded and fetched"


def test_the_reason_for_an_exclusion_says_it_was_not_fetched():
    """The record is read by someone who was not here. "Excluded" without a
    reason is a gap; with one it is a decision they can disagree with."""
    for name, why in probe.EXCLUDED.items():
        assert "NOT FETCHED" in why["why"], name
        assert "robots" in why["why"].lower(), name


def test_readable_drops_scripts_and_styles():
    """A term inside a `<script>` is not something the page says. Counting it
    would make a vendor's analytics config into a product claim."""
    markup = ("<html><script>var x = 'degree audit';</script>"
              "<style>.a{content:'pathway'}</style>"
              "<p>Course planning for schools</p></html>")
    text = probe.readable(markup)
    assert "degree audit" not in text
    assert "pathway" not in text
    assert "course planning for schools" in text


def test_recording_nothing_is_refused(monkeypatch, capsys, tmp_path):
    """No vendor answering at all is a network problem, not a finding —
    writing it would record the whole field as silent."""
    monkeypatch.setattr(probe, "RECORD", tmp_path / "c.json")
    monkeypatch.setattr(probe, "measure", lambda: {
        "vendors": {"X": {"reachable": True, "fetched": False}},
        "excluded": {}})
    monkeypatch.setattr(probe, "report", lambda f: None)
    assert probe.main(["--record"]) == 3
    assert "no vendor page answered" in capsys.readouterr().err
    assert not (tmp_path / "c.json").exists()


def test_this_file_opens_no_sockets():
    """The docstring says nothing here fetches. Asserted, not trusted.

    **Inlined, and temporarily.** `tests/no_sockets.py` holds this runner and
    arrives with #184, which is not merged — so importing it here would be a
    claim about a file that is not in this tree, which is exactly the mistake
    #184's review caught. Delete this in favour of that helper the moment it
    lands on `main`.

    `connect_ex` as well as `connect`: a guard watching one of them is green
    against the other.
    """
    import pathlib as _pathlib
    import subprocess
    import sys

    root = _pathlib.Path(__file__).resolve().parents[1]
    target = _pathlib.Path(__file__).resolve().relative_to(root).as_posix()
    watcher = f"""
import socket
hits = []
class Watch(socket.socket):
    def connect(self, addr):
        hits.append(addr)
        return super().connect(addr)
    def connect_ex(self, addr):
        hits.append(addr)
        return super().connect_ex(addr)
socket.socket = Watch
import pytest
pytest.main(['-q', '--no-header', '-p', 'no:cacheprovider', {target!r},
             '--deselect', {target + '::test_this_file_opens_no_sockets'!r}])
print('CONNECTS', len(hits))
"""
    result = subprocess.run([sys.executable, "-c", watcher], cwd=str(root),
                            capture_output=True, text=True, timeout=180)
    reported = [n for n in result.stdout.splitlines() if n.startswith("CONNECTS")]
    assert reported, (
        f"the watcher did not report.\nrc={result.returncode}\n"
        f"stderr:\n{result.stderr[-500:]}")
    assert reported[-1] == "CONNECTS 0", (
        f"{reported[-1]} — a test in this file reached the network")
