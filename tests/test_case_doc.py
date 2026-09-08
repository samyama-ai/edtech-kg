"""`docs/standards/case.md` held to the record that produced it.

The page answers edtech-kg#32 — do academic standards become a node tier —
and the answer is no for a reason that is easy to overstate. "Not reachable"
is a claim about access on a date, not about the standards existing, and the
tests below hold the page to the narrower one.

Whitespace is collapsed before matching, so reflowing unchanged prose does
not fail these.

Nothing reaches the network.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "standards" / "case.md"
RECORD = json.loads((ROOT / "docs" / "standards"
                     / "case-measured.json").read_text("utf-8"))
PAGE = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
NET, SALT, FL = RECORD["case_network"], RECORD["opensalt"], RECORD["cpalms"]


def test_every_case_path_has_a_row_and_every_row_is_measured():
    """The table IS route one. A path measured and left off it is a path
    whose absence changes the verdict."""
    for path, found in NET["paths"].items():
        row = re.search(rf"\| `{re.escape(path)}` \| (\d+) \| (\d+) \|", PAGE)
        assert row, f"{path}'s row no longer parses"
        assert int(row.group(1)) == found["status"]
        assert int(row.group(2)) == found["bytes"]
    said = re.search(r"\*\*(\d+) of (\d+) paths serve CASE JSON", PAGE)
    assert said, "the page no longer counts the paths serving CASE JSON"
    assert int(said.group(1)) == len(NET["serves_case_json"])
    assert int(said.group(2)) == len(NET["paths"])


def test_the_registry_is_reported_unreachable_because_it_measured_so():
    assert NET["reachable_as_data"] is False, (
        "the registry now serves CASE JSON; the page's route-one conclusion "
        "no longer holds and needs rewriting rather than re-running")
    assert any(f["status"] == 403 for f in NET["paths"].values()), (
        "no path refused with 403; the page cites one")


def test_opensalt_is_reported_as_a_sandbox_with_its_evidence():
    """"A working CASE endpoint holding demonstration data" is a claim about
    WHO authored the documents, so the creators have to be on the page."""
    said = re.search(r"\*\*(\d+) documents from (\d+)\s*creators\*\*", PAGE)
    assert said, "the page no longer states OpenSALT's population"
    assert int(said.group(1)) == SALT["documents"]
    assert int(said.group(2)) == SALT["distinct_creators"]

    top = {c for c, _ in SALT["top_creators"][:6]}
    shown = set(re.findall(r"\| ([^|]+?) \| \d+ \|", PAGE))
    assert top & shown, (
        f"none of the recorded creators {sorted(top)} is on the page; the "
        f"sandbox claim rests on who authored these")
    assert SALT["documents_with_a_licence_uri"] == 0, (
        "documents now carry a licence URI; the page says none do")


def test_the_cpalms_zero_is_the_measured_one():
    """Route three, and the one that would have changed the verdict. A state
    publishing a course-to-standard alignment in its markup is the edge the
    issue says makes standards worth having."""
    said = re.search(
        r"\*\*(\d+) links to a standard\*\* and \*\*(\d+) standard codes\*\*",
        PAGE)
    assert said, "the page no longer states the CPALMS counts"
    assert int(said.group(1)) == FL["standard_links"]
    assert int(said.group(2)) == FL["standard_codes"]
    assert FL["status"] == 200, (
        "CPALMS no longer answers 200; a zero from a page that did not load "
        "is a different finding")


def test_the_page_does_not_claim_the_standards_are_absent():
    """The overreach this finding invites. The standards are published and
    real; what is missing is a machine route, and the page has to keep those
    apart or it reads as a claim about US education."""
    assert "Nothing here says the standards are absent" in PAGE
    for overreach in ("the standards do not exist",
                      "no state publishes standards"):
        assert overreach not in PAGE.lower()


def test_the_page_states_the_403_is_a_refusal_to_this_client():
    """An account or an agreement might open the registry, and none was
    sought. Saying so is the difference between "we could not get in" and
    "there is nothing there"."""
    assert "refusal to" in PAGE and "none was sought" in PAGE
    assert "no unauthenticated machine route was found" in PAGE


def test_the_measurement_is_dated_and_says_to_re_run():
    """A host that refuses today may serve tomorrow, and the registry was
    rebranded once already."""
    assert RECORD["retrieved_at"] in PAGE
    assert "Re-run the probe" in PAGE
