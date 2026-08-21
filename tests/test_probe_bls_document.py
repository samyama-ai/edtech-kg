"""The document says what the probe measured — `docs/sources/bls-occupation.md`.

Split from `tests/test_probe_bls_access.py` at 503 lines, over the limit review
will read. Split by SUBJECT, the standard this repo set when
`test_schema_cypher.py` was split: this file checks that the PAGE keeps up with
what the probe found, and the access tests check how bls.gov is reached.

The claim has got ahead of the evidence twice in this repo, which is why the
page is asserted against the probe rather than read and trusted.
"""

from __future__ import annotations

import json
import pathlib
import re

from etl import bls_access as access
from etl import probe_bls as probe
from tests.bls_fixtures import page, row, serve

DOCUMENT = (pathlib.Path(__file__).resolve().parents[1]
            / "docs" / "sources" / "bls-occupation.md")


# --------------------------------------------------------------------------
# the document says what the probe measured
# --------------------------------------------------------------------------

def test_the_absent_codes_are_named_on_the_page_not_only_in_json():
    r"""The page used to say the thirteen were "named in the probe's --json
    output" — a reference a reader cannot check without a network and a
    crosswalk file. The codes belong on the page.

    The page's own two statements are compared against each other: the count
    in the table, and the codes in the block below it. A literal set of
    thirteen codes in this file would be a third copy of a measurement that
    changes with every projections release — the exact staleness this file
    guards against elsewhere, reintroduced by its own test.

    `\b\d{2}-\d{4}\b` matches any NN-NNNN, so the codes are read from the
    fenced block rather than from anywhere on the page: a phone fragment or a
    page range elsewhere would otherwise make the count agree by accident.
    """
    text = DOCUMENT.read_text()
    stated = re.search(r"\*\*Absent outright\*\*\s*\|\s*\*\*(\d+)\*\*", text)
    assert stated, "the page no longer states an absent-outright count"

    block = re.search(r"```\n((?:\s*\d{2}-\d{4}\s*)+)```", text)
    assert block, (
        "the page states a count of absent occupations but does not list them; "
        "a reader cannot see which occupations we cannot answer for")
    listed = set(re.findall(r"\b\d{2}-\d{4}\b", block.group(1)))
    assert len(listed) == int(stated.group(1)), (
        f"the page says {stated.group(1)} occupations are absent outright and "
        f"lists {len(listed)}. Re-run the probe and update both.")


def test_the_probe_prints_the_absent_codes_and_does_not_only_count_them(monkeypatch, capsys):
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: {"13-2011", "21-1011"})
    monkeypatch.setattr(access, "head",
                        lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(access, "attempt", lambda url, agent=None: {"status": 200})
    probe.probe()
    printed = capsys.readouterr().out
    assert "21-1011" in printed, "the absent code was counted but never named"


def test_the_agent_table_in_the_document_has_a_row_per_agent():
    """A matrix that grows in the probe and not on the page is how the claim
    got ahead of the evidence the last two times."""
    text = DOCUMENT.read_text()
    heading = "| User-Agent |"
    # Split blindly and a renamed heading raises IndexError with nothing in it
    # to say which table moved.
    assert heading in text, f"no {heading!r} table in {DOCUMENT.name}"
    block = text.split(heading)[1].split("\n\n")[0]
    rows = [line for line in block.splitlines()
            if line.startswith("|") and not set(line) <= set("|-: ")]
    assert len(rows) == len(access.AGENTS), \
        f"the document shows {len(rows)} agents; the probe sends {len(access.AGENTS)}"


def test_the_document_states_the_release_it_was_generated_against():
    text = DOCUMENT.read_text()
    assert re.search(r"\*\*May 20\d\d release\*\*", text), "no OEWS release vintage stated"
    # Whitespace-collapsed: the document is hard-wrapped, so a phrase test that
    # matches the raw text is really testing where the line breaks fall.
    flat = " ".join(text.split()).lower()
    # The CLAIM, not one phrasing of it. "found by the probe rather than
    # written down" is one sentence a rewrite would innocently change while
    # saying exactly the same thing, and a test that fails on that teaches
    # people to edit the test rather than read it.
    assert "probe" in flat and any(
        phrase in flat for phrase in
        ("rather than written down", "rather than remembered",
         "found rather than", "not written down", "not hard-coded")), \
        "the vintage reads as remembered rather than measured"
    # The reason a status check is not enough has to survive on the page, or
    # the next person restores the cheaper check.
    assert "text/html" in flat and "404" in flat, \
        "the soft-404 behaviour that makes status insufficient is not recorded"


def test_an_unreachable_source_exits_two(monkeypatch):
    monkeypatch.setattr(probe, "projections",
                        lambda: (_ for _ in ()).throw(RuntimeError("dns")))
    assert probe.main([]) == 2


def test_a_malformed_source_exits_three(monkeypatch):
    monkeypatch.setattr(probe, "projections",
                        lambda: (_ for _ in ()).throw(probe.MalformedSource("layout")))
    assert probe.main([]) == 3


def test_json_output_carries_a_timestamp(monkeypatch, capsys):
    serve(monkeypatch, page(row("13-2011")))
    monkeypatch.setattr(probe, "crosswalk_soc", lambda: set())
    monkeypatch.setattr(access, "head", lambda url: {"status": 200, "bytes": 1, "is_file": True})
    monkeypatch.setattr(access, "attempt",
                        lambda url, agent=None: {"status": 200 if agent else 403})
    assert probe.main(["--json"]) == 0
    assert "retrieved_at" in json.loads(capsys.readouterr().out)


