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
    # EVERY spelling checked, and the whole key set recorded. The first
    # version counted `licenceUri` — the British spelling, in no version of
    # the specification — so the zero was a property of the key name rather
    # than of the server, and the fixture fed the same misspelling so the
    # code only agreed with itself.
    for field, n in SALT["documents_by_licence_field"].items():
        row = re.search(rf"\| `{re.escape(field)}` \| (\d+) \|", PAGE)
        assert row, f"{field}'s row is not on the page"
        assert int(row.group(1)) == n
    assert "licenseUri" in SALT["documents_by_licence_field"], (
        "the CASE spec spelling is not among the fields checked")
    assert not any(SALT["documents_by_licence_field"].values()), (
        "a licence field is now populated; the page's claim that the licence "
        "question cannot be answered from the data no longer holds")
    assert "licenseUri" not in SALT["keys_observed"], (
        "the key set says licenseUri IS published; the counts and the key "
        "set disagree and one of them is wrong")


def test_the_cpalms_rows_are_the_measured_ones():
    """Route three. **Three course ids, not one** — a single page carrying no
    alignment is consistent with several explanations, and three identical
    ones leave one."""
    for page in FL["pages"]:
        row = re.search(
            rf"\| {page['course_id']} \| (\d+) \| ([\d,]+) \| (\d+) \|", PAGE)
        assert row, f"course {page['course_id']}'s row no longer parses"
        assert int(row.group(1)) == page["status"]
        assert int(row.group(2).replace(",", "")) == page["bytes"]
        assert int(row.group(3)) == page["standard_links"]
    assert FL["answered"] == len(FL["pages"]), (
        "a CPALMS page did not answer; a zero from a page that did not load "
        "is a different finding")


def test_the_shell_finding_rests_on_both_halves_of_its_evidence():
    """Identical bytes ALONE could be a coincidence of length. It is
    conclusive because no page carries its own course id."""
    said = re.search(
        r"\*\*(\d+) distinct document for (\d+) course\s*ids\.\*\*", PAGE)
    assert said, "the page no longer states the distinct-document count"
    assert int(said.group(1)) == FL["distinct_documents"]
    assert int(said.group(2)) == len(FL["pages"])
    assert FL["serves_one_document_for_every_course"] is True, (
        "CPALMS now serves distinct documents per course; route 3 measured "
        "something else and the section needs rewriting")
    assert not any(p["names_its_own_course_id"] for p in FL["pages"]), (
        "a page names its own course id, so identical bytes no longer prove "
        "a shell")


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
    assert RECORD["retrieved_at"] in PAGE, (
        f"the page does not carry the measurement date "
        f"{RECORD['retrieved_at']}")
    assert "Re-run the probe" in PAGE
