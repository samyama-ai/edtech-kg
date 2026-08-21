"""The engine client — how a value becomes a literal, and what a reply means.

`lit()` is the whole of the injection defence, because 1.1.0's `/api/query`
takes no parameters and has no escape sequence inside a string literal. It had
no test at all until review said so.

Reading the catalogue is `tests/test_pwcs_source.py`; writing it is
`tests/test_load_pwcs.py`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import etl.engine as module
from etl.engine import Engine, Unquotable, lit
from etl.pwcs_source import read

CACHE = Path(__file__).resolve().parents[1] / "data" / "pwcs"

# `read()` walks 960 pages. Cached they are local and instant; cold it is 960
# requests to a school district from a test run. `data/` is gitignored, so a
# fresh clone has none of it, and these would hammer the source rather than
# fail. Skipped instead — with the command that makes them runnable.
# A PARTIAL cache is worse than none: `read()` finds most pages locally and
# fetches the rest from the district. Counted, not merely "not empty".
CACHED_PAGES = len(list(CACHE.glob("*"))) if CACHE.exists() else 0

needs_cache = pytest.mark.skipif(
    CACHED_PAGES < 900,
    reason=(f"cached catalogue is incomplete ({CACHED_PAGES} of ~960 pages) — "
            f"run `python -m etl.probe_pwcs` first"))


@pytest.fixture
def replies(monkeypatch):
    """Stand one canned reply in for the engine, and record what was sent.

    `monkeypatch`, not a hand-rolled try/finally around the stdlib global.
    Four tests each saved and restored `urllib.request.urlopen` themselves —
    boilerplate where a test failing between the swap and the finally leaves
    every later test talking to a stub.

    **The patch is process-wide, and monkeypatch is what makes it safe.**
    `module.urllib.request` is the same module object every importer sees, so
    naming it through `etl.engine` confines nothing — an earlier version of
    this docstring claimed it did. What confines the damage is the teardown:
    pytest restores the attribute even when the test raises, which the four
    try/finally blocks did only when they were reached.
    """
    def install(payload: bytes):
        sent = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return payload

        def urlopen(request, timeout=None):
            sent["url"] = request.full_url
            sent["method"] = request.get_method()
            sent["body"] = request.data
            sent["headers"] = dict(request.header_items())
            return Response()

        monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
        return sent

    return install


# --------------------------------------------------------------------------
# lit() — 1.1.0 has no escape sequence, so the quote choice IS the defence
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("plain", "'plain'"),
    ("Governor's School", '"Governor\'s School"'),
    ('say "hi"', "'say \"hi\"'"),
    ("back\\slash", "'back\\slash'"),
    (None, "null"),
    (3, "3"),
    (1.5, "1.5"),
])
def test_a_value_is_wrapped_in_the_quote_it_does_not_contain(value, expected):
    assert lit(value) == expected


def test_a_bool_is_not_rendered_as_a_number():
    """`isinstance(True, int)` is true, so the bool branch has to come first.
    Load-bearing ordering, and untested until now.

    Deliberately not a row in the table above — the table asserts renderings,
    this asserts a branch ORDER, and a row saying `True -> "true"` states the
    outcome without saying what it is guarding."""
    assert lit(True) == "true"
    assert lit(False) == "false"
    assert lit(1) == "1", "an int must still render as a number"


def test_a_value_holding_both_quotes_is_refused_not_mangled():
    """1.1.0 supports no escape sequence inside a string literal — not `\\'`,
    not `''`, not `\\"` — so a value containing both quote characters cannot be
    expressed at all, and `/api/query` takes no parameters to fall back on.

    Raising is the point. A course silently loaded under a different name than
    the district published is the failure nothing downstream would show.
    """
    with pytest.raises(Unquotable):
        lit("""Governor's "School\"""")


def test_a_quote_cannot_terminate_the_literal_early():
    """The property being defended: whatever wrapper is chosen, the value does
    not contain it, so nothing can close the string early."""
    for value in ("O'Brien", 'the "best" course', "plain"):
        rendered = lit(value)
        assert rendered[0] == rendered[-1], rendered
        assert rendered[0] not in value, rendered


def test_a_non_finite_float_is_refused_rather_than_sent():
    """`str(float('nan'))` is `nan`, which 1.1.0 does not parse. Sent, the
    statement is rejected at the far end with a message about the whole query
    rather than about the value; refused here, the offending value is named."""
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(Unquotable):
            lit(value)


@needs_cache
def test_no_value_in_this_catalogue_is_unquotable():
    """Stated as a measurement rather than a hope — if a future catalogue
    breaks it, this says so rather than the loader raising mid-run.

    The count is asserted. The loop alone proved nothing: `read()` returning
    empty lists, or records whose fields are all None, ran zero `lit()` calls
    and passed — reporting a measurement nobody had made.
    """
    data = read()
    checked = 0
    for record in data["subjects"] + data["courses"] + data["pathways"]:
        for value in (record["url"], record["title"], record.get("requirements_text")):
            if value:
                lit(value)
                checked += 1
    assert checked > 1_000, (
        f"only {checked} values were quotable-checked; the catalogue holds "
        f"~1,000 pages, so this measured almost nothing")


# --------------------------------------------------------------------------
# the engine client
# --------------------------------------------------------------------------

def test_a_well_formed_reply_is_decoded_and_the_request_is_shaped_right(replies):
    """The happy path, which nothing covered: every other test here asserts a
    failure, so a client that decoded correctly and posted to the wrong URL —
    or sent the query under the wrong key — would have passed the whole file."""
    sent = replies(b'{"columns": ["n"], "records": [[7]]}')
    engine = Engine("http://engine:8080/", graph="edtech")

    assert engine.run("MATCH (n) RETURN count(n)") == {
        "columns": ["n"], "records": [[7]]}
    assert sent["url"] == "http://engine:8080/api/query", sent["url"]
    assert sent["method"] == "POST", sent["method"]
    assert json.loads(sent["body"]) == {
        "query": "MATCH (n) RETURN count(n)", "graph": "edtech"}
    assert sent["headers"].get("Content-type") == "application/json", sent["headers"]
    assert engine.statements == 1


def test_scalar_returns_the_one_value(replies):
    replies(b'{"columns": ["c"], "records": [[795]]}')
    assert Engine("http://x").scalar("MATCH (n:Course) RETURN count(n)") == 795


def test_a_rejected_statement_is_an_error_even_though_the_status_was_200(replies):
    """The engine answers 200 with an `error` key for a parse failure."""
    replies(b'{"error": "Parse error: unexpected token"}')
    with pytest.raises(RuntimeError, match="Parse error"):
        Engine("http://x").run("MATCH (n) RETURN n")


def test_a_non_object_response_says_so_rather_than_asking_it_for_a_key(replies):
    """`"error" in result` on a string asks about substrings — a different
    question that happens not to raise."""
    replies(b'"just a string"')
    with pytest.raises(RuntimeError, match="not an object"):
        Engine("http://x").run("MATCH (n) RETURN n")


def test_a_reply_with_no_records_key_names_the_statement(replies):
    """`run(query)["records"]` raised a bare KeyError naming a string, which
    says nothing about which statement produced it — the one failure shape this
    class otherwise works to eliminate."""
    replies(b'{"columns": ["n"]}')
    with pytest.raises(RuntimeError, match="without records"):
        Engine("http://x").scalar("MATCH (n) RETURN count(n)")


def test_scalar_does_not_confuse_no_rows_with_a_null_value(replies):
    """It returned None for three different things — no rows, an empty row, and
    a null. A caller cannot tell "matched nothing" from "the query is wrong"."""
    replies(b'{"columns": ["n"], "records": []}')
    with pytest.raises(RuntimeError, match="no rows at all"):
        Engine("http://x").scalar("MATCH (n:Nothing) RETURN count(n)")

    replies(b'{"columns": ["n"], "records": [[]]}')
    with pytest.raises(RuntimeError, match="no columns"):
        Engine("http://x").scalar("MATCH (n:Nothing) RETURN count(n)")

    replies(b'{"columns": ["n"], "records": [[null]]}')
    assert Engine("http://x").scalar("MATCH (n) RETURN n.missing") is None, \
        "a null the engine actually returned is a value, not an absence"


def test_no_attempts_is_a_caller_error_not_an_engine_fault():
    """`attempts=0` skipped the retry loop and fell through with `result =
    None`, which the shape check then reported as the ENGINE answering with a
    NoneType — a message describing a server fault for a bad argument."""
    with pytest.raises(ValueError, match="at least 1"):
        Engine("http://x").run("MATCH (n) RETURN n", attempts=0)


def test_an_unquotable_property_stops_before_the_node_is_written(replies):
    """`upsert` validated identifiers up front but rendered property values
    inside the second statement, so an Unquotable one raised AFTER the MERGE
    had landed — leaving a node that exists, carries its key, and has none of
    its properties. Nothing downstream distinguishes that from a node the
    source says nothing about."""
    sent = replies(b'{"columns": [], "records": []}')
    engine = Engine("http://x")
    with pytest.raises(Unquotable):
        module.upsert(engine, "Course", "url", "https://t/a",
                      {"title": """it's a "problem\""""})
    assert engine.statements == 0, "the MERGE was sent before the value was checked"
    assert not sent, "nothing should have reached the engine"


def test_a_transient_failure_is_retried_and_a_permanent_one_is_not(monkeypatch):
    """`attempts` was asserted only through its rejection of 0 — nothing proved
    a transient failure is actually retried, which is the whole reason the
    parameter exists. A 503 is worth another go; a 400 will fail identically
    every time and retrying only delays the report."""
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    class Response:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self): return b'{"columns": [], "records": []}'

    calls = []

    def flaky(request, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise module.urllib.error.HTTPError(
                request.full_url, 503, "Service Unavailable", {}, None)
        return Response()

    monkeypatch.setattr(module.urllib.request, "urlopen", flaky)
    engine = Engine("http://x")
    assert engine.run("MATCH (n) RETURN n") == {"columns": [], "records": []}
    assert len(calls) == 3, f"expected two retries then a success, got {len(calls)}"
    assert engine.retries == 2, engine.retries

    permanent = []

    def refused(request, timeout=None):
        permanent.append(1)
        raise module.urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr(module.urllib.request, "urlopen", refused)
    with pytest.raises(RuntimeError, match="400"):
        Engine("http://x").run("MATCH (n) RETURN n")
    assert len(permanent) == 1, (
        f"a 400 fails identically every time; retrying it {len(permanent)}x "
        f"only delays the report")
