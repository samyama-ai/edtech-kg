"""What `docs/sources/sced.md` CLAIMS, against what the probe measures.

Split out of `tests/test_probe_sced.py` when it passed the 500-line review
limit, on the boundary the other probes already use — `test_probe_sced.py`
drives the parsing, and this reads the page.

Every blocker this branch has had was a published claim rather than a bug: a
count typed instead of printed, a table that did not add up, a figure counted
against the wrong crosswalk. The parsing was right each time.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "sources" / "sced.md"


def plain() -> str:
    """The page as one line, emphasis stripped.

    A name that WRAPS does not contain the newline and one that gains bold no
    longer matches — both silently turn a text assertion into no assertion.
    The same shape fixed on the apprenticeship pages.
    """
    text = DOC.read_text(encoding="utf-8")
    return " ".join(text.replace("*", "").replace("`", "").split())


def test_the_document_quotes_only_figures_the_probe_produces():
    """Every figure on `docs/sources/sced.md` comes from the probe, and each
    pin names its own ROW.

    The two halves were separate tests and the reviewer was right that they
    overlapped. Anchoring is the point of both: `"791"` matched `**1,791**` on
    the version row, so the figure the pin existed to guard was never checked
    — a guard that passes on a different number reads as coverage. The other
    test's `page.count("791") >= 2` asserted only that both figures were
    somewhere, which the anchored rows already prove. The ones
    that would go stale first are the version and the two counts the argument
    rests on, so those are pinned by name rather than by value — a changed
    figure fails here instead of being quoted for another month."""
    page = DOC.read_text(encoding="utf-8")
    # ANCHORED. `"791"` matched `**1,791**` on the version row, so the figure
    # it meant to guard — `PWCS courses loaded | **791**` — was unpinned: the
    # assertion passed on a different number entirely. Same for the bare
    # `2,012` and `2,001`, which the rows below now pin in place.
    for claim in ("SCED 13.0",
                  "| Courses | **1,791** |",
                  "| Rows in the sheet | **2,012** |",
                  "| Five-digit SCED codes | **2,001** |",
                  "| PWCS courses loaded | **791** |",
                  "67 — 8%",
                  # The element/attribute split. Pinned because the page now
                  # quotes the two counts, and a figure on the page that
                  # nothing guards is the drift this test exists to stop.
                  "Elements a record may carry | **6**",
                  "Attributes it may also carry | **17**"):
        assert claim in page, f"the page no longer states {claim!r}"
    assert "Publishing a SCED code | **0**" in page, (
        "the page no longer states that the district publishes no SCED code — "
        "which is the finding the schema decision rests on")

    # The three figures added with the resolution fix, pinned the same way. A
    # figure on the page that nothing guards is the drift this test exists to
    # stop, and these are the ones that make the headline honest: the strict
    # comparison it is measured against, and the two counts that say the
    # headline is not quietly counting a state extension.
    for claim in ("without the parenthetical rule it is **58** rather than 67",
                  "| Matches resolving to a New York **state extension** | **0** |",
                  "| Titles New York publishes under more than one code | **203** |"):
        assert claim in page, f"the page no longer states {claim!r}"


def test_the_document_does_not_claim_sced_solves_prerequisites():
    """The sequence element's name invites exactly that conclusion, and the
    page exists partly to refuse it."""
    page = DOC.read_text(encoding="utf-8").lower()
    assert "part n of m" in page or "part 'n' of 'm'" in page, (
        "the page no longer explains what the sequence element means")
    assert re.search(r"not a (relationship|prerequisite) between", page), (
        "the page no longer says the sequence element is not a prerequisite")


def test_the_exhibits_on_the_page_are_the_ones_the_probe_prints():
    """The page promised nothing is typed and its two exhibit blocks were.

    `district_reach` emits NORMALISED keys, so `AP Biology` and `IB Physics
    (SL)` — which normalise to `biology` and `physics` — cannot have come from
    it, and the unmatched list had no producer at all. The lists were true,
    which is a lesser sin than wrong, and still not reproducible.

    Both are printed now, and this asserts the page shows what the run does.
    """
    from etl import new_york_catalog, probe_sced, sced_reach

    page = plain()
    ny = new_york_catalog.new_york(
        probe_sced.fetch(new_york_catalog.NEW_YORK))
    reach = sced_reach.district_reach(ny["titles"], set(ny["state_extensions"]))

    for title in reach["matched_titles"]:
        assert title in page, (
            f"the page's matched exhibit does not carry {title!r}, which the "
            f"probe prints — so the block was written rather than generated")
    for title in reach["unmatched_titles"]:
        assert title in page, (
            f"the page's unmatched exhibit does not carry {title!r}")


def test_the_cte_courses_the_page_names_really_are_unmatched():
    """The prose names four CTE programmes as what SCED misses.

    That is the argument, not an illustration, so it is asserted against the
    catalogue rather than remembered — and the four were correct when checked,
    which is why the claim stays.
    """
    from etl import new_york_catalog, probe_sced, sced_reach
    from etl import pwcs_source

    ny = new_york_catalog.new_york(
        probe_sced.fetch(new_york_catalog.NEW_YORK))
    by_name, _ = sced_reach.resolve_titles(ny["titles"],
                                           set(ny["state_extensions"]))
    catalogue = [c["title"] for c in pwcs_source.read()["courses"]]
    page = plain()

    for name in ("Turfgrass Management", "Landscaping 1",
                 "Horticulture Sciences",
                 "Greenhouse Plant Production & Management"):
        assert name in page, f"the page no longer names {name!r}"
        found = [t for t in catalogue if name.lower() in t.lower()]
        assert found, f"{name!r} is not in the loaded catalogue at all"
        assert all(sced_reach.normalise(t) not in by_name for t in found), (
            f"{name!r} is named as unmatched and SCED reaches it")
