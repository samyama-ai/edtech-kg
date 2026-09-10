"""`docs/sources/who-sells-this.md` held to the run that produced it.

edtech-kg#47. The page is a survey of what vendors PUBLISH, and the thing
that makes it honest rather than an opinion is that every count on it came
out of one recorded run over pages we were permitted to fetch.

Two of the tests here are about permission rather than about figures, because
on this issue the permission decisions were the interesting part: one vendor
was excluded without being fetched, and the reason has to survive on the page.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "sources" / "who-sells-this.md"
RECORD_PATH = ROOT / "docs" / "sources" / "competitors-measured.json"

PAGE = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
RECORD = (json.loads(RECORD_PATH.read_text(encoding="utf-8"))
          if RECORD_PATH.exists() else {})


def test_the_page_and_the_record_are_both_here():
    assert DOC.exists(), "the page is missing"
    assert RECORD_PATH.exists(), (
        "no record; `python -m etl.probe_competitors --record` writes it")


def test_every_vendor_measured_is_on_the_page():
    """A vendor measured and left off is one a reader cannot know about, and
    the awkward ones are the tempting omission."""
    for name in RECORD["vendors"]:
        assert name in PAGE, f"{name} was measured and is absent from the page"


def test_every_term_count_on_the_page_is_the_measured_one():
    """Anchored to the vendor's row, not loose in the prose — a count against
    the wrong vendor would otherwise pass."""
    for name, v in RECORD["vendors"].items():
        if not v.get("fetched"):
            continue
        row = re.search(rf"^\| {re.escape(name)} \|(.*)\|$", PAGE, re.M)
        assert row, f"{name} has no row"
        for term, n in v["terms"].items():
            if n:
                assert f"`{term}` {n}" in row.group(1), (
                    f"the page's row for {name} does not carry {term}={n}")


def test_both_lengths_are_on_the_page():
    """**A term count of zero over NO text is a reader artefact; over 8,105
    characters it is a finding.** The page carries both so the two cannot be
    confused — `case.md` shipped a `bytes: 0` that was an artefact of a
    discarded response body, and this is the same trap one page over.
    """
    for name, v in RECORD["vendors"].items():
        if not v.get("fetched"):
            continue
        assert f"{v['bytes']:,}" in PAGE, f"{name}'s byte length is missing"
        assert f"{v['text_chars']:,}" in PAGE, (
            f"{name}'s readable length is missing, so a zero count cannot be "
            f"told from an empty page")


def test_the_excluded_vendor_was_never_fetched():
    """**The permission decision this issue turned on.** Coursicle's
    robots.txt disallows a list of AI user-agents; ours is not on it, so a
    parser permits the fetch. It was not fetched.

    The record must show it as excluded and carry no measurement for it — an
    "excluded" vendor with a byte count would mean we fetched it and then
    said we had not.
    """
    assert RECORD["excluded"], "nothing is recorded as excluded"
    for name, why in RECORD["excluded"].items():
        assert name not in RECORD["vendors"], (
            f"{name} is both excluded and measured")
        assert "bytes" not in why, f"{name} was excluded but carries a measurement"
        assert "NOT FETCHED" in why["why"]
        assert name in PAGE, f"{name}'s exclusion is not on the page"


def test_the_page_says_what_it_does_not_establish():
    """One page per vendor, on one day. A front page is a marketing choice,
    not an inventory — and Naviance certainly does course planning whatever
    its 404s say."""
    assert "does not establish" in PAGE.lower()
    assert "not a capability comparison" in PAGE.lower()


def test_a_vendor_that_did_not_answer_is_not_recorded_as_refusing():
    """A company that has stopped trading and one that blocks us are
    different facts. The issue expects LTS to be the first."""
    for name, v in RECORD["vendors"].items():
        if v.get("reachable") is False:
            assert "unreachable" in PAGE.lower()
            assert v.get("status") is None, (
                f"{name} is unreachable and carries a status code")


def test_the_record_was_written_by_a_clean_tree():
    if not RECORD:
        pytest.skip("no record")
    assert RECORD["code"]["dirty"] is False


def measured():
    """The vendors that actually answered — not everyone named."""
    return {n: v for n, v in RECORD["vendors"].items() if "terms" in v}


def test_the_page_counts_only_the_vendors_that_answered():
    """**An unmeasured vendor was counted as a silent one.** The page said
    "five of six do not use it at all" while six were named and five
    answered — LTS Education is recorded `reachable: false` with no term
    counts, so it was being read as a vendor measuring zero rather than as a
    vendor we could not measure.

    That is the same error as `or 0` on an unreadable count: the difference
    between "we asked and the answer was none" and "we never got to ask" is
    the whole point of the section above.
    """
    #: Spelled out because the page is prose. Kept here rather than in the
    #: page so the figure still comes from the record.
    WORD = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
            6: "six"}
    silent = [n for n, v in measured().items()
              if v.get("says_nothing_about_planning")]
    expected = f"{WORD[len(silent)]} of the {WORD[len(measured())]}"
    assert expected in PAGE.lower(), (
        f"the page should say {expected!r} — {len(silent)} of the "
        f"{len(measured())} vendors that answered say nothing about planning")
    unreachable = [n for n, v in RECORD["vendors"].items() if "terms" not in v]
    assert unreachable, "no unreachable vendor in the record to guard against"
    # The CLAIM, not any mention — the paragraph above it quotes the old
    # wording to say what was corrected, and that should not trip this.
    named = WORD[len(RECORD["vendors"])]
    assert f"of {named} do not use" not in PAGE.lower(), (
        f"the page counts all {len(RECORD['vendors'])} named vendors where "
        f"only {len(measured())} answered; {unreachable} never did")


def test_the_terms_nobody_uses_are_the_measured_ones():
    """#47's own definition of done calls this "the only part that changes
    what we build", so it is pinned to the record like every other figure
    here rather than left as prose."""
    unused = sorted(t for t in RECORD["terms_counted"]
                    if all(v["terms"][t] == 0 for v in measured().values()))
    assert unused, "no term is unused; the section's claim no longer holds"
    for term in unused:
        assert re.search(rf"\| `{re.escape(term)}` \| 0 of {len(measured())} \|",
                         PAGE), (
            f"`{term}` is used by no vendor in the record and the page's "
            f"table does not say so")
    # And the other direction: nothing is claimed unused that somebody uses.
    for row in re.findall(r"^\| `([^`]+)` \| 0 of \d+ \|$", PAGE, re.M):
        assert row in unused, (
            f"the page says `{row}` is used by nobody; the record disagrees")


def test_the_three_terms_this_repo_is_built_on_are_named():
    """The claim the section turns on. If a vendor ever starts using one of
    them, this fails rather than the page quietly overstating the gap."""
    ours = ("prerequisite", "graduation requirement", "course plan")
    for term in ours:
        assert term in RECORD["terms_counted"], (
            f"{term!r} is not counted by the probe, so the page cannot claim "
            f"anything about it")
        users = [n for n, v in measured().items() if v["terms"][term] > 0]
        assert not users, (
            f"the page says no vendor uses {term!r}; {users} do")
