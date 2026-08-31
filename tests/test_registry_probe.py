"""Driving `probe` — the sampling, the refusal channels, the record it writes.

Split from `tests/test_registry_licence.py` when it passed the 500-line review
limit. Split by SUBJECT: that file exercises the READERS — the three terms
sentences, the vocabulary search, what counts as a record saying something —
and checks the page against the committed record. This one drives `probe`
itself.

**Nothing here reaches the network, and one test proves it.** `drive_probe`
closes every door `probe` can reach out through; `total` was missing from that
list once and four live requests went to the Credential Registry on every run.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import registry_licence as rl
from tests.test_registry_licence import RECORD, TERMS_PAGE, VOCABULARY

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "registry-data-licence.md"


@pytest.fixture(scope="module")
def record() -> dict:
    """Its own, rather than imported — an imported fixture binds a module
    global that every test taking `record` then shadows."""
    return json.loads(RECORD.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# the borrowed fetching layer, and everything that is "not the document asked
# for". `probe` imports `etl.registry_read` lazily, so these patch the module
# it will import rather than a name bound at import time.
# --------------------------------------------------------------------------

def drive_probe(monkeypatch, *, get=None, parse=None, page_text=None,
                total=None):
    """Every door `probe` can reach the network through, closed.

    `total` was missing, and it is not optional: `probe` calls it once per
    resource type to size the sample, so four live HEAD requests to the
    Credential Registry went out on every run of this file — under a docstring
    saying nothing here fetches. Measured: four socket connections.

    The default population is a real one (the course search returned 47,862),
    so `sample_pages` spreads over a realistic number of pages rather than
    collapsing to a single one and hiding a stride bug.
    """
    from etl import registry_read
    monkeypatch.setattr(rl, "page_text",
                        page_text or (lambda url, timeout=60: TERMS_PAGE))
    monkeypatch.setattr(rl, "graph_of", lambda payload, what: VOCABULARY_GRAPH)
    monkeypatch.setattr(registry_read, "total", total or (lambda path: 47_862))
    monkeypatch.setattr(registry_read, "get", get or (lambda url: b"[]"))
    monkeypatch.setattr(registry_read, "parse", parse or (lambda body, what: []))


VOCABULARY_GRAPH = [{"@id": "ceterms:copyrightHolder"}]


def test_a_registry_outage_is_refused_rather_than_a_traceback(monkeypatch):
    """`registry_read` raises its OWN classes, and one shares this module's name.

    `main` catches `registry_licence.MalformedSource`. `registry_read.get`
    raises `HttpStatus`, and its `parse` raises a DIFFERENT class also called
    `MalformedSource`, so a 503 from the Registry produced a traceback and no
    exit code — while `page_text`, three lines up, converts exactly this into
    a refusal for the pages it fetches itself.
    """
    from etl.registry_read import HttpStatus

    def boom(url):
        raise HttpStatus(503, url)

    drive_probe(monkeypatch, get=boom)
    with pytest.raises(rl.MalformedSource, match="search"):
        rl.probe(quiet=True)
    assert rl.main(["--json"]) == 3


def test_a_search_page_that_is_not_json_is_refused(monkeypatch):
    from etl.registry_read import MalformedSource as ReadRefused

    def bad(body, what):
        raise ReadRefused(f"{what} did not parse as JSON")

    drive_probe(monkeypatch, parse=bad)
    with pytest.raises(rl.MalformedSource, match="did not parse as JSON"):
        rl.probe(quiet=True)


def test_a_search_page_that_is_an_object_is_refused_not_counted(monkeypatch):
    """An error body that is a JSON object extended `envelopes` with its KEYS.

    `carrying_a_rights_field` then called `.get` on a `str`. `probe_registry`
    already guards this because the Registry has returned other shapes; this
    module diverged from it.
    """
    drive_probe(monkeypatch,
                parse=lambda body, what: {"error": "rate limited"})
    with pytest.raises(rl.MalformedSource, match="not a list of envelopes"):
        rl.probe(quiet=True)


@pytest.mark.parametrize("payload,expected", [
    ("<html>502 Bad Gateway</html>", "did not parse as JSON"),
    ('["not", "an", "object"]', "no @graph list"),
    ('{"nope": 1}', "no @graph list"),
    ('{"@graph": {"a": 1}}', "no @graph list"),
])
def test_a_vocabulary_that_is_not_the_vocabulary_is_refused(payload, expected):
    """`json.loads(...)["@graph"]` fails three ways, none of them catchable."""
    with pytest.raises(rl.MalformedSource, match=expected):
        rl.graph_of(payload, "the CTDL vocabulary")


@pytest.mark.parametrize("envelope", [
    {"decoded_resource": None},
    {"decoded_resource": "a string"},
    {"decoded_resource": {"@graph": None}},
    {"decoded_resource": {"@graph": {"ceterms:copyrightHolder": "x"}}},
    {"decoded_resource": {"@graph": ["ceterms:copyrightHolder"]}},
])
def test_a_misshapen_envelope_counts_as_saying_nothing(envelope):
    """The count must not crash, and must not report a field that is not there.

    A non-list `@graph` iterates its KEYS, so `field in node` became a
    substring test against a string — which would have reported a rights field
    on a record that carries none, on the page whose whole finding is that
    zero records carry one.
    """
    got = rl.carrying_a_rights_field([envelope])
    assert got == {"envelopes": 1, "carrying_copyright_holder": 0,
                   "fields_looked_for": list(rl.RIGHTS_FIELDS),
                   "read_or_measured": "measured"}


def test_the_page_quotes_no_split_the_record_does_not_hold(record):
    """"75 each" was the PLAN — 25 per page times three pages, times four types.

    The record holds one flat total. If any type returned short the JSON would
    stay self-consistent, every count test would still pass, and the page's
    per-type breakdown would be quietly false.
    """
    page = PAGE.read_text()
    # Both spellings. The page writes thousands with commas and the record
    # holds an int, so `str(398)` matched today and `str(1234)` would not have
    # — a check that works only while the number stays small.
    envelopes = record["records"]["envelopes"]
    assert (str(envelopes) in page or f"{envelopes:,}" in page), (
        f"the page does not state the {envelopes} records the record holds")
    assert "75 each" not in page
    per_kind = re.search(r"(\d+) each of", page)
    assert not per_kind, f"the page quotes a per-type split the record lacks: {per_kind}"


def test_the_record_states_how_each_type_was_sampled(record):
    """The blocking finding of the second review, pinned.

    The first version read pages 1, 2 and 3 of each search consecutively —
    which is not a sample of the Registry, it is a sample of whatever sorts
    first. `registry_read.sample_pages` exists to prevent exactly that, and
    `describe` reports what the walk reached. Both are now used, and the
    description is carried into the record so a reader can see the shape of
    the sample rather than take it on trust.
    """
    sampling = record["records"]["sampling"]
    assert set(sampling) == {"course", "credential",
                             "learning_opportunity_profile", "pathway"}
    for kind, how in sampling.items():
        assert how, f"{kind} has no sampling description"
        # Either the pages were spread, or the whole population was read.
        # "biased toward whatever sorts first" is `describe`'s own wording for
        # the head sample, and it must not appear.
        assert ("stride" in how or "whole population" in how), \
            f"{kind} was not spread and is not exhaustive: {how}"
        assert "biased toward whatever sorts first" not in how, \
            f"{kind} is a head sample: {how}"


def test_the_page_repeats_the_sampling_the_record_holds(record):
    """A reader cannot check a sample whose shape is not on the page.

    The record alone is not enough — the document is what anyone reads, and
    the review's point was that neither said pages 1-3 had been taken off the
    head. The stride figures are quoted, so the page cannot drift back to
    claiming a spread it did not have.
    """
    page = re.sub(r"\s+", " ", PAGE.read_text())
    for kind, how in record["records"]["sampling"].items():
        if "stride" not in how:
            continue
        stride = re.search(r"stride of ([\d,]+)", how).group(1)
        # The page writes thousands with a comma; the description may not.
        variants = {stride, f"{int(stride.replace(',', '')):,}"}
        assert any(f"stride of {v}" in page for v in variants), \
            f"the page does not state {kind}'s stride ({stride})"


def test_probe_spreads_the_pages_it_asks_for(monkeypatch):
    """The mutation the record-based tests could not see.

    Those tests read `registry-licence-measured.json`, which is committed — so
    reverting `probe` to `range(1, 4)` left them green while the next
    `--record` would have written a head sample. The pages actually requested
    have to be checked against the code, not against a file the code wrote
    last time.
    """
    from etl import registry_read
    from etl import registry_licence as rl

    asked: list[str] = []

    def fake_get(url):
        asked.append(url)
        return b"[]"

    monkeypatch.setattr(registry_read, "total", lambda path: 47_862)
    monkeypatch.setattr(registry_read, "get", fake_get)
    monkeypatch.setattr(registry_read, "parse",
                        lambda body, what: [{"decoded_resource": {"@graph": [{}]}}])
    monkeypatch.setattr(rl, "page_text", lambda url, timeout=60: (
        TERMS_PAGE if url == rl.TERMS_URL else json.dumps({"@graph": VOCABULARY})))

    rl.probe(quiet=True)

    pages = [int(re.search(r"[?&]page=(\d+)", u).group(1)) for u in asked]
    assert pages, "probe asked for nothing"
    # Not 1, 2, 3. With a population this size the stride is large, so the
    # highest page read must be far past the head.
    assert max(pages) > 100, f"pages were taken off the head: {sorted(set(pages))}"
    assert len(set(pages)) > 1, "only one page was read, so nothing is spread"


def test_probe_records_how_it_sampled(monkeypatch):
    """`sampling` must reach the result, or the record has nothing to state.

    Emptying it left every record-based assertion green, because those read
    the committed file rather than a fresh run.
    """
    from etl import registry_read
    from etl import registry_licence as rl

    monkeypatch.setattr(registry_read, "total", lambda path: 47_862)
    monkeypatch.setattr(registry_read, "get", lambda url: b"[]")
    monkeypatch.setattr(registry_read, "parse",
                        lambda body, what: [{"decoded_resource": {"@graph": [{}]}}])
    monkeypatch.setattr(rl, "page_text", lambda url, timeout=60: (
        TERMS_PAGE if url == rl.TERMS_URL else json.dumps({"@graph": VOCABULARY})))

    sampling = rl.probe(quiet=True)["records"]["sampling"]
    assert set(sampling) == {"course", "credential",
                             "learning_opportunity_profile", "pathway"}
    for kind, how in sampling.items():
        assert "stride" in how, f"{kind} was not described as spread: {how}"


def test_this_file_opens_no_sockets():
    """The docstring says nothing here fetches. It was not true.

    `drive_probe` patched `page_text`, `graph_of`, `get` and `parse` but not
    `total` — which `probe` calls once per resource type to size the sample —
    so four live HEAD requests went to the Credential Registry on every run of
    this file, and it took six seconds. It takes well under one now.

    Asserted rather than trusted: a missing patch is invisible until somebody
    watches the socket, and the next helper added here can reintroduce it.

    **The paths are DERIVED, not written.** Hardcoding them survived a file
    rename by pointing the deselect at a module that no longer held this test
    — so the child ran it too, and it ran a child of its own, and the run had
    to be killed. A self-referential guard must find itself.
    """
    import subprocess
    import sys

    target = pathlib.Path(__file__).resolve().relative_to(ROOT).as_posix()
    watcher = f"""
import socket
hits = []
class Watch(socket.socket):
    def connect(self, addr):
        hits.append(addr)
        return super().connect(addr)
socket.socket = Watch
import pytest
pytest.main(['-q', '--no-header', '-p', 'no:cacheprovider',
             {target!r},
             '--deselect', {target + '::test_this_file_opens_no_sockets'!r}])
print('CONNECTS', len(hits))
"""
    result = subprocess.run([sys.executable, "-c", watcher],
                            capture_output=True, text=True,
                            cwd=str(ROOT), timeout=120)
    reported = [line for line in result.stdout.splitlines()
                if line.startswith("CONNECTS")]
    assert reported, f"the watcher did not report:\n{result.stdout[-600:]}"
    assert reported[-1] == "CONNECTS 0", (
        f"{reported[-1]} — a test in this file reached the network. Something "
        f"`probe` calls is unpatched; `total` was the one that hid here.")


def test_the_record_carries_the_verdict_not_only_the_evidence(record):
    """The committed record states the conclusion, not only the evidence."""
    verdict = record.get("verdict", "")
    assert verdict, "the record states no verdict"
    assert "not cleared" in verdict.lower()
    assert "developer agreement" in verdict.lower(), (
        "the verdict does not say what would change the answer")


def test_scope_counts_the_uncleared_rows_it_actually_lists():
    """The paragraph said two while the table held three.

    It is prose about a table three lines above it, so it drifts every time a
    row is added — which is exactly what happened when this PR added the
    Registry row. Counted from the table rather than trusted.
    """
    scope = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    rows = re.findall(r"(?m)^\| (?!Source\b)(?!-)([^|]+)\|([^|]*)\|([^|]*)\|$", scope)
    assert rows, "the scope licence table could not be read"
    uncleared = [r for r in rows
                 if "not cleared" in r[2].lower() or "not settled" in r[2].lower()
                 or "not yet checked" in r[2].lower()]
    claimed = re.search(r"\*\*(\w+) of those are not cleared\*\*", scope)
    assert claimed, "scope.md no longer states how many rows are not cleared"
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    assert words[claimed.group(1).lower()] == len(uncleared), (
        f"scope.md claims {claimed.group(1)} uncleared rows; the table has "
        f"{len(uncleared)}: {[r[0].strip() for r in uncleared]}")


def test_probe_puts_the_verdict_in_what_it_writes(monkeypatch):
    """The committed record cannot test the code that writes it.

    Reading `registry-licence-measured.json` and asserting the verdict is in
    it passes whatever `probe` does, because the file is checked in — the
    third time in this repo that a record-based assertion has looked like
    coverage and been none. Removing the verdict from `probe` has to fail.
    """
    drive_probe(monkeypatch)
    verdict = rl.probe(quiet=True).get("verdict", "")
    assert "not cleared" in verdict.lower(), "probe emits no verdict"
    assert "developer agreement" in verdict.lower(), (
        "the verdict does not say what would change the answer, which is the "
        "difference between a refusal and a dead end")


def test_the_documented_command_does_not_crash(monkeypatch, capsys):
    """`python -m etl.registry_licence` raised KeyError, and shipped.

    A field was renamed and the print path was not swept with it, so the one
    invocation both the module docstring and the page tell people to run died
    on `records['carrying_a_rights_field']` after printing two thirds of its
    output.

    Nothing caught it because **every other test passes `quiet=True`** — the
    reporting path had no coverage at all, so a name it references could go
    stale without a single assertion noticing.
    """
    drive_probe(monkeypatch)
    rl.probe()                                   # quiet=False — the crash path
    printed = capsys.readouterr().out
    assert "records inspected" in printed
    assert "saying anything about their own terms" in printed
    assert "how each type was sampled" in printed


def test_the_reporting_path_reads_only_keys_the_result_has(monkeypatch):
    """The class, not the instance.

    One stale key crashed the command. Every key the print block reads is
    checked against the result it is handed, so the next rename fails here
    rather than in front of whoever runs the probe.
    """
    import re as _re

    drive_probe(monkeypatch)
    result = rl.probe(quiet=True)
    source = (ROOT / "etl" / "registry_licence.py").read_text(encoding="utf-8")

    for path in _re.findall(r"result\['(\w+)'\]\['(\w+)'\]", source):
        outer, inner = path
        assert outer in result, f"the print block reads result[{outer!r}]"
        assert inner in result[outer], (
            f"the print block reads result[{outer!r}][{inner!r}], which the "
            f"result does not have — a rename left the reporting path behind")


def test_a_registry_outage_while_sizing_is_refused_not_a_traceback(monkeypatch):
    """`total` sat outside the conversion, one call before the one that had it.

    Sizing the sample reaches the Registry too, so a 503 there escaped `main`
    as a traceback — the exact failure the borrowed-layer bridge was added to
    prevent, one line earlier than it was guarding.
    """
    from etl.registry_read import HttpStatus

    def down(path):
        raise HttpStatus(503, f"{path} is unavailable")

    drive_probe(monkeypatch, total=down)
    with pytest.raises(rl.MalformedSource, match="sizing the .* sample"):
        rl.probe(quiet=True)


def test_every_date_for_this_source_agrees_with_the_record(record):
    """Three places state when the terms were read, and they drifted.

    `docs/scope.md`'s row said 2026-08-28 while the page and the record said
    2026-08-31 — the row was written in one round and the measurement redone
    in another. A reader takes whichever they meet first.
    """
    import re as _re

    read_on = record["retrieved_at"]
    scope = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    row = [line for line in scope.splitlines()
           if line.startswith("| Credential Registry")]
    assert row, "the Credential Registry row is no longer in the scope table"
    dates = set(_re.findall(r"\d{4}-\d{2}-\d{2}", row[0]))
    assert dates == {read_on}, (
        f"the scope row states {sorted(dates)}; the record was read on "
        f"{read_on}")

    page = PAGE.read_text(encoding="utf-8")
    claimed = _re.search(r"Read on \*\*(\d{4}-\d{2}-\d{2})\*\*", page)
    assert claimed and claimed.group(1) == read_on
