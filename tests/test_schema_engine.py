"""The schema against a running engine.

    docker run --rm -p 8201:8080 public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
    SAMYAMA_URL=http://localhost:8201 \\
    SAMYAMA_TEST_URL=http://localhost:8201 pytest tests/test_schema_engine.py

Two variables, deliberately. `SAMYAMA_URL` is where the constraints are
executed — DDL only, nothing written. `SAMYAMA_TEST_URL` is for the tier-4
traversals, which CREATE and DETACH DELETE, and which refuse an engine already
holding nodes. A writing test finding an engine by accident is how a loaded demo
graph gets damaged, and it has happened once already in a sibling repo.

`SAMYAMA_REQUIRE_ENGINE=1` turns an unreachable engine into a failure rather
than a skip. Skipping silently is how "verified against the engine" reaches a
README on the strength of a run nobody made.

The parse tests are in `tests/test_schema_cypher.py`; the readers both
files use are in `tests/schema_source.py`.
"""

from __future__ import annotations

import io
import json
import os
import re
import urllib.error
import urllib.request

import pytest

from tests.schema_source import SCHEMA_DOC, section, statements

SAMYAMA_URL = os.environ.get("SAMYAMA_URL", "http://localhost:8080")


def engine_available():
    try:
        urllib.request.urlopen(f"{SAMYAMA_URL}/api/tenants", timeout=2).read()
        return True
    except Exception:
        return False


def query(url, statement):
    """One statement, one reply. `{"error": …}` for anything that went wrong,
    because the caller's job is to report which statement broke — an exception
    escaping here loses that.

    One helper, used by both the constraint test and the traversals. There were
    two, differing only in which URL they read from a module global."""
    request = urllib.request.Request(
        f"{url}/api/query",
        data=json.dumps({"query": statement}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
        # A 200 carrying something that is not JSON — a proxy page, a truncated
        # reply — raised out of here, losing the statement that caused it. The
        # caller's job is to report WHICH statement broke, so every failure has
        # to come back in the same shape.
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return {"error": f"a 200 that is not JSON: {exc}",
                    "transport": True}
    except urllib.error.HTTPError as exc:
        # 5xx is the ENGINE FAILING, not the engine refusing. A 400 carrying a
        # parse error is a genuine rejection and the thing two tests below are
        # asserting; a 500 from a dying engine looks identical to them without
        # this flag — which is the exact failure the flag was introduced to
        # close, left open on the one branch that has a readable body.
        transport = exc.code >= 500
        try:
            return {"error": exc.read().decode(errors="replace")[:300],
                    "transport": transport}
        except Exception:  # noqa: BLE001
            return {"error": f"HTTP {exc.code}, and the body could not be read",
                    "transport": True}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"error": f"engine unreachable mid-run: {exc}", "transport": True}


def run(statement):
    return query(SAMYAMA_URL, statement)


def test_schema_executes_against_the_engine():
    """Every statement runs clean against a live instance.

    Run against a FRESH instance: constraints are validated against existing
    data, so leftover nodes surface here as a false failure.

    `SAMYAMA_REQUIRE_ENGINE=1` turns an unreachable engine into a failure.
    Skipping this silently is how "verified against the engine" ends up in a
    README on the strength of a run nobody made.
    """
    if not engine_available():
        message = f"no Samyama engine at {SAMYAMA_URL}"
        if os.environ.get("SAMYAMA_REQUIRE_ENGINE") == "1":
            pytest.fail(f"{message} — SAMYAMA_REQUIRE_ENGINE=1 forbids skipping this")
        pytest.skip(message)

    for statement in statements():
        result = run(statement)
        assert "error" not in result, f"{statement[:70]} -> {result.get('error')}"


# --------------------------------------------------------------------------
# the tier-4 shapes, actually run
# --------------------------------------------------------------------------
#
# `docs/schema.md` carries a table headed "The tier-4 shapes were run, not
# assumed", with four ✅ against four traversal forms. Nothing executed them.
# The page is otherwise careful to say which claims are observed rather than
# tested, and a ✅ beside an unexecuted query is the one thing on it that
# outran its evidence.
#
# These require **`SAMYAMA_TEST_URL`**, not `SAMYAMA_URL`, and refuse an engine
# that already holds nodes. They write and DETACH DELETE; the constraint test
# above only issues DDL. Pointing a writing test at a demo engine has to be a
# decision somebody typed:
#
#     docker run --rm -p 8201:8080 public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
#     SAMYAMA_TEST_URL=http://localhost:8201 pytest tests/test_schema_engine.py

TEST_URL = os.environ.get("SAMYAMA_TEST_URL")

# A prerequisite ladder four deep, plus a branch that leaves the subject — so
# "reached depth 3 across a subject boundary" is a property of the fixture and
# not a hopeful reading of one.
FIXTURE = [
    "CREATE (:Course {url: 'https://t/art/1', name: 'Art 1', subject: 'Art', src: 'fx'})",
    "CREATE (:Course {url: 'https://t/art/2', name: 'Art 2', subject: 'Art', src: 'fx'})",
    "CREATE (:Course {url: 'https://t/art/3', name: 'Art 3', subject: 'Art', src: 'fx'})",
    "CREATE (:Course {url: 'https://t/art/4', name: 'Art 4', subject: 'Art', src: 'fx'})",
    "CREATE (:Course {url: 'https://t/math/1', name: 'Math 1', subject: 'Math', src: 'fx'})",
    "MATCH (a:Course {url:'https://t/art/2'}), (b:Course {url:'https://t/art/1'}) CREATE (a)-[:REQUIRES]->(b)",
    "MATCH (a:Course {url:'https://t/art/3'}), (b:Course {url:'https://t/art/2'}) CREATE (a)-[:REQUIRES]->(b)",
    "MATCH (a:Course {url:'https://t/art/4'}), (b:Course {url:'https://t/art/3'}) CREATE (a)-[:REQUIRES]->(b)",
    # The boundary crossing: an Art course requiring a Math course.
    "MATCH (a:Course {url:'https://t/art/3'}), (b:Course {url:'https://t/math/1'}) CREATE (a)-[:REQUIRES]->(b)",
]


def rows(url, statement):
    result = query(url, statement)
    assert "error" not in result, f"{statement[:90]} -> {result['error']}"
    # Not `result["records"]`: a 200 carrying neither `error` nor `records`
    # gives a bare KeyError naming a string, which is the one traceback shape
    # this module otherwise works to eliminate.
    assert "records" in result, (
        f"{statement[:90]} -> the engine answered without an error and without "
        f"records: {result}")
    return result["records"]


@pytest.fixture
def empty_engine():
    """A reachable, EMPTY engine — the guards, and nothing written.

    Split out of `ladder` so a test about the schema alone does not run against
    fixture data. Constraints are validated against existing rows, so a change
    to the ladder could surface as a schema failure and send the next person
    reading the wrong file.
    """
    if not TEST_URL:
        message = "no engine at SAMYAMA_TEST_URL"
        if os.environ.get("SAMYAMA_REQUIRE_ENGINE") == "1":
            pytest.fail(f"{message} — SAMYAMA_REQUIRE_ENGINE=1 forbids skipping this")
        pytest.skip(f"{message} — set it to a FRESH instance, never a loaded one")
    try:
        urllib.request.urlopen(f"{TEST_URL}/api/tenants", timeout=2).read()
    except Exception:
        if os.environ.get("SAMYAMA_REQUIRE_ENGINE") == "1":
            pytest.fail(f"nothing answering at {TEST_URL}")
        pytest.skip(f"nothing answering at {TEST_URL}")

    held = rows(TEST_URL, "MATCH (n) RETURN count(n)")[0][0]
    # `if held:` on a string is truthy for "0" — an engine returning the count
    # as text would report an empty instance as loaded. Coerced first, and a
    # value that will not coerce is reported rather than guessed at.
    try:
        held = int(held)
    except (TypeError, ValueError):
        pytest.fail(f"the engine answered the node count with {held!r}, which "
                    f"is not a number — this guard cannot tell whether the "
                    f"instance is empty")
    if held:
        # `int()` first: `f"{held:,}"` raises TypeError on a string, and the
        # engine returning a count as text would then crash the guard instead
        # of reporting the graph it found — an error about formatting, in the
        # message whose job is to say "point this somewhere else".
        pytest.fail(
            f"SAMYAMA_TEST_URL points at an engine holding {held:,} nodes. These "
            f"tests write and DETACH DELETE; use a fresh instance.")
    return TEST_URL


@pytest.fixture
def ladder(empty_engine):
    """A fresh engine holding only the fixture, torn down afterwards.

    Every statement below goes to `empty_engine`, the value this fixture
    depends on — not to the module-global `TEST_URL`. They are the same string
    today, so reading the global worked; it also meant the dependency was
    decorative, and a change to how the URL is resolved would have left this
    writing to whatever the global happened to hold.
    """
    # try/finally: a FIXTURE statement that fails used to abort before `yield`,
    # so the teardown never ran and the nodes it had already written stayed —
    # making every later run fail the "engine holding N nodes" guard above, for
    # a reason that looks nothing like the original failure.
    try:
        for statement in FIXTURE:
            result = query(empty_engine, statement)
            assert "error" not in result, f"{statement[:70]} -> {result['error']}"
        yield empty_engine
    finally:
        query(empty_engine, "MATCH (n) WHERE n.src = 'fx' DETACH DELETE n")


def test_q65_what_must_i_take_first_returns_the_full_ancestor_set(ladder):
    """`(t)-[:REQUIRES*1..10]->(need)` — outbound, depth not known in advance."""
    got = {r[0] for r in rows(ladder,
        "MATCH (:Course {name:'Art 4'})-[:REQUIRES*1..10]->(n:Course) RETURN n.name")}
    assert got == {"Art 3", "Art 2", "Art 1", "Math 1"}, got


def test_q61_blast_radius_reaches_across_a_subject_boundary(ladder):
    """Q61 is the inbound question — what closes off if this course is missed —
    but it is written here as an OUTBOUND match ending at Math 1, which walks
    the same edges and lets `length(path)` be returned per starting course.
    The doc's row states the inbound form; both name one traversal.

    The fixture is built to make the claim checkable: Math 1 is required by
    Art 3, which Art 4 reaches at depth 2."""
    got = rows(ladder,
        "MATCH path = (c:Course)-[:REQUIRES*1..10]->(:Course {name:'Math 1'}) "
        "RETURN c.name, c.subject, length(path)")
    assert {(r[0], r[2]) for r in got} == {("Art 3", 1), ("Art 4", 2)}, got
    assert {r[1] for r in got} == {"Art"}, (
        "every course reaching Math 1 should be an Art course — if not, the "
        "fixture no longer crosses a subject boundary and Q61 proves nothing")


def test_q66_deepest_chain_is_found_without_being_told_the_depth(ladder):
    """`max(length(p))`. The ladder is four deep; a query that had to be told
    the depth could not discover that."""
    got = rows(ladder,
        "MATCH path = (:Course)-[:REQUIRES*1..10]->(:Course) "
        "RETURN max(length(path))")
    assert got[0][0] == 3, f"expected the Art 4 -> Art 1 chain at depth 3, got {got}"


def test_q62_shortest_route_between_two_courses(ladder):
    """`shortestPath((a)-[:REQUIRES*]-(b))`. Art 4 reaches Art 1 in three hops
    down the ladder; the Math branch is not a shorter way round.

    **Both endpoints must be bound to a variable.** Written with anonymous
    nodes — `shortestPath((:Course {name:'Art 4'})-[…]->(:Course {…}))` — 1.1.0
    answers `Planning error: shortestPath target must have a variable`. That is
    the form this test was first written in, and the doc's ✅ beside this row
    had never been executed in any form. It is a constraint on how the query is
    written, not on what the engine can answer.
    """
    got = rows(ladder,
        "MATCH (a:Course {name:'Art 4'}), (b:Course {name:'Art 1'}) "
        "MATCH path = shortestPath((a)-[:REQUIRES*1..10]->(b)) "
        "RETURN length(path)")
    assert got and got[0][0] == 3, got


def test_shortest_path_needs_a_variable_on_both_ends(ladder):
    """Recorded as a test so the finding survives, and so the day it stops
    being true this file says so rather than a document going quietly stale."""
    result = query(ladder,
        "MATCH path = shortestPath((:Course {name:'Art 4'})-[:REQUIRES*1..10]->"
        "(:Course {name:'Art 1'})) RETURN length(path)")
    # That it is REFUSED is the finding. The wording is the engine's and may
    # change without the behaviour changing; pinning it makes this test fail on
    # a release note rather than on a regression. The day the form is accepted,
    # this goes red and the document above needs its note removed.
    assert "error" in result, (
        "1.1.0 refused shortestPath with anonymous endpoints; if it no longer "
        "does, drop the note in docs/schema.md that says it does")
    # A transport failure is not a refusal. `query()` reports an unreachable
    # engine, a timeout, an unreadable error body or a non-JSON 200 in the same
    # `{"error": …}` shape as a planning rejection, so this passed on the engine
    # dying mid-run — recording a finding that had not been reproduced.
    #
    # Asked as a FLAG rather than by matching one wording: excluding the string
    # "unreachable mid-run" left the other three synthesised failures still
    # reading as refusals.
    assert not result.get("transport"), (
        f"the engine went away rather than refusing the query, so this proves "
        f"nothing about 1.1.0: {result['error']}")


def test_the_doc_marks_every_tier_four_row_this_file_executes():
    """The table and these tests must not drift apart. Each ✅ row names a
    question number; every one of them has a test above, and that is asserted
    from the document rather than remembered."""
    body = section(SCHEMA_DOC.read_text(), "The tier-4 shapes were run")
    blocks = body.split("\n\n")
    assert len(blocks) > 1, (
        "the tier-4 table no longer follows that heading after a blank line")
    table = blocks[1]
    claimed = set(re.findall(r"\| (Q\d+)", table))
    assert claimed, "no question numbers in the tier-4 table — did it change shape?"
    # The slice must be the TABLE, not merely something with Q-numbers in it.
    # `section()` returning an unexpected span — a heading reworded, a blank
    # line moved — would otherwise be papered over by any prose that mentions
    # a question number.
    assert table.lstrip().startswith("|"), (
        f"the slice taken as the tier-4 table does not start with a table row, "
        f"so it is not the table: {table[:80]!r}")

    # Read off this module's own test names rather than a hand-kept literal.
    # A literal makes the guard say what somebody last remembered: delete a
    # test and the set still claims it runs, which is the drift this exists to
    # catch, arriving from the side the author is not looking at.
    tested = {name.split("_")[1].upper() for name in globals()
              if re.fullmatch(r"test_q\d+_\w+", name)}
    assert tested, "no test_q<n>_ functions found — has the naming changed?"
    assert claimed == tested, (
        f"docs/schema.md claims {sorted(claimed)} were run; this file executes "
        f"{sorted(tested)}")


def test_applying_the_schema_twice_changes_nothing(empty_engine):
    """Re-running the file must be safe, because the loader applies it on every
    run. Other Cypher engines error on an already-present constraint, which is
    why the reflex is to ask for `IF NOT EXISTS` — a form 1.1.0 does not parse.

    So the property is asserted rather than assumed. If a future release starts
    refusing, this fails and `apply_schema` needs a guard.

    Against `empty_engine`, not `ladder`: a constraint is validated against the
    rows already present, so running this on fixture data would let a change to
    the ladder surface as a schema failure.
    """
    for pass_number in (1, 2):
        for statement in statements():
            result = query(empty_engine, statement)
            assert "error" not in result, (
                f"pass {pass_number} of the schema failed on "
                f"{statement[:70]} -> {result.get('error')}")


def test_naming_and_dropping_a_constraint_or_index_are_parse_errors(empty_engine):
    """Recorded so the finding survives review rather than being re-litigated.

    "Name the constraints so a specific one can be replaced" is sound advice
    against an engine that accepts names. This one does not: the named
    CONSTRAINT form, the named INDEX form and `DROP CONSTRAINT` are all parse
    errors — so naming would buy nothing even if it parsed. The day any of them
    is accepted, this goes red and the note in schema/edtech_kg.cypher needs
    removing.
    """
    for statement in (
        "CREATE CONSTRAINT probe_named ON (x:ProbeNamed) ASSERT x.k IS UNIQUE",
        "CREATE INDEX probe_named_idx ON :ProbeNamed(k)",
        "DROP CONSTRAINT ON (x:ProbeNamed) ASSERT x.k IS UNIQUE",
    ):
        result = query(empty_engine, statement)
        assert "error" in result, f"1.1.0 now accepts {statement!r}"
        assert not result.get("transport"), (
            f"the engine went away rather than refusing: {result['error']}")

    # `SHOW CONSTRAINTS` does parse — what is declared can at least be read.
    assert "error" not in query(empty_engine, "SHOW CONSTRAINTS")


def test_a_constraint_declares_the_key_and_does_not_enforce_it(ladder):
    """The claim the whole MERGE rule rests on, measured rather than repeated.

    If 1.1.0 ever starts rejecting the duplicate, this fails — and the schema's
    "loaders must MERGE" paragraph becomes advice rather than the only thing
    standing between a re-run and a doubled graph.

    **This leaves a constraint behind, and it cannot be removed.** `DROP
    CONSTRAINT` is a parse error in 1.1.0 — asserted two tests up — so the
    `DupProbe` declaration outlives the run. That is safe here and worth
    knowing: a constraint declares a key without enforcing it, so an inherited
    one changes nothing about a later test, and the fixture's guard counts
    NODES, which the teardown does remove. The alternative is not cleaning up
    better, it is a fresh container per test.
    """
    assert "error" not in query(
        ladder, "CREATE CONSTRAINT ON (u:DupProbe) ASSERT u.k IS UNIQUE")
    first = query(ladder, "CREATE (:DupProbe {k: 'same', src: 'fx'})")
    second = query(ladder, "CREATE (:DupProbe {k: 'same', src: 'fx'})")
    assert "error" not in first, first
    assert "error" not in second, (
        "1.1.0 now rejects a duplicate against a declared key — the schema says "
        "it does not, and every 'loaders must MERGE' note rests on that")
    held = rows(ladder, "MATCH (n:DupProbe) RETURN count(n)")[0][0]
    assert int(held) == 2, f"expected both duplicates to be stored, got {held!r}"


def test_a_5xx_is_a_transport_failure_and_a_400_is_a_refusal(monkeypatch):
    """The distinction two tests in this file rest on.

    `query()` reports every failure in one `{"error": …}` shape, so the tests
    asserting "1.1.0 REFUSED this" need a way to tell a refusal from a dying
    engine. The flag was set for a non-JSON 200, an unreadable body and a
    URLError — and NOT for an HTTPError with a readable body, which is exactly
    what a 500 from a failing engine looks like. Both refusal tests would have
    passed on an engine failure: the failure the flag exists to close.

    A 400 carrying a parse error is a genuine rejection and must NOT be
    flagged, or those tests would skip the finding they exist to record.
    """
    def failing(code, body):
        def urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                "http://x", code, "boom", {}, io.BytesIO(body))
        return urlopen

    monkeypatch.setattr(urllib.request, "urlopen", failing(500, b"upstream died"))
    got = query("http://x", "MATCH (n) RETURN n")
    assert got.get("transport") is True, got

    monkeypatch.setattr(urllib.request, "urlopen",
                        failing(400, b'{"error": "Parse error: unexpected token"}'))
    got = query("http://x", "MATCH (n) RETURN n")
    assert "error" in got, got
    assert not got.get("transport"), (
        "a 400 parse error was flagged as a transport failure, which would make "
        "every 'the engine refused this' test skip its own finding")
