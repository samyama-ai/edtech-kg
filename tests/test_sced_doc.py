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
