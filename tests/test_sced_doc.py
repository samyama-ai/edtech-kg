"""What `docs/sources/sced.md` CLAIMS, against what the probe measures.

Split out of `tests/test_probe_sced.py` when it passed the 500-line review
limit, on the boundary the other probes already use — `test_probe_sced.py`
drives the parsing, and this reads the page.

Every blocker this branch has had was a published claim rather than a bug: a
count typed instead of printed, a table that did not add up, a figure counted
against the wrong crosswalk. The parsing was right each time.
"""

from __future__ import annotations

import json
import pathlib
import re
from pathlib import Path

import pytest

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


RECORD = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "docs" / "sources"
     / "sced-measured.json").read_text(encoding="utf-8"))


def test_the_exhibits_on_the_page_are_the_ones_the_probe_printed():
    """Both directions, against the committed record rather than a live run.

    `district_reach` emits NORMALISED keys, so `AP Biology` and `IB Physics
    (SL)` could not have come from it and the unmatched list had no producer
    at all. The lists were true and not reproducible.

    Checked against `docs/sources/sced-measured.json`, not by re-measuring:
    `pwcs_source.read()` walks a sitemap and fetches whatever is missing,
    which from CI means ~960 requests to one school district on every push —
    the traffic `conftest.py` exists to refuse, in as many words. This runs in
    milliseconds and still means "the page shows what the probe printed";
    `test_the_record_still_matches_the_live_sources` re-measures where the
    cache exists.

    BOTH directions, and scoped to the block. The first version asserted
    probe → page over the whole document, so a ninth invented name would pass
    — and `Turfgrass Management` appears in the prose as well as the exhibit,
    which is how a whole-document match hides that.
    """
    page = DOC.read_text(encoding="utf-8")
    for key, heading in (("matched_titles", "already national:"),
                         ("unmatched_titles", "the district's own:")):
        expected = RECORD["district"][key]
        block = " ".join(_block_after(page, heading).replace("·", " ").split())
        for title in expected:
            assert title in block, (
                f"the {key} block does not carry {title!r}, which the probe "
                f"printed — so the block was written rather than generated")
        # And nothing else. Every name in the block must be one of them.
        leftover = block
        for title in sorted(expected, key=len, reverse=True):
            leftover = leftover.replace(title, "")
        assert not leftover.strip(), (
            f"the {key} block carries {leftover.strip()!r}, which is in no "
            f"measured run — a name in an exhibit that came from nowhere")


def _block_after(page: str, heading: str) -> str:
    """The indented exhibit under one heading, and nothing else.

    Matching the whole document lets a name that appears in the prose stand in
    for one in the block — `Turfgrass Management` is in both.
    """
    after = page.split(heading, 1)[1]
    lines = []
    for line in after.splitlines():
        if line.startswith("    "):
            lines.append(line.strip())
        elif lines:
            break
    assert lines, f"no indented block under {heading!r}"
    return " ".join(lines)


def test_the_figures_on_the_page_are_the_ones_the_probe_printed():
    """`New York publishes eight columns` and the eleven extension codes were
    typed — the probe printed only their COUNTS.

    Both were mutated in the page (eight → nineteen, invented codes) and the
    suite stayed green.
    """
    page = plain()
    ny = RECORD["new_york"]

    assert f"{len(ny['columns'])} columns" in page.lower() or \
        f"{_spelled(len(ny['columns']))} columns" in page.lower(), (
        f"the page does not state the {len(ny['columns'])} columns New York "
        f"publishes")
    for column in ny["columns"]:
        assert column in page, f"the page does not name the column {column!r}"
    # BOTH directions, as with the exhibits. Every recorded code on the page,
    # and no code on the page that is not recorded — the first version checked
    # only one way, so an invented code passed.
    import re as _re
    on_page = set(_re.findall(r"\b\d{5}[A-Z]{1,2}\b", page))
    assert on_page == set(ny["state_extensions"]), (
        f"the page names {sorted(on_page - set(ny['state_extensions']))} which "
        f"no run produced, and omits "
        f"{sorted(set(ny['state_extensions']) - on_page)}")


def _spelled(n: int) -> str:
    return {8: "eight", 11: "eleven"}.get(n, str(n))


def test_the_cte_courses_the_page_names_really_are_unmatched():
    """The prose names four CTE programmes as what SCED misses — the argument,
    not an illustration.

    Against the RECORD, not a live catalogue. This called `pwcs_source.read()`,
    which from CI means ~960 requests to one school district; the record
    carries which of them were measured unmatched, and
    `test_the_record_still_matches_the_live_sources` keeps that honest.
    """
    page = plain()
    measured = RECORD["district"]["named_cte_unmatched"]
    assert measured, "the record carries no CTE measurement to check against"

    for name in ("Turfgrass Management", "Landscaping 1",
                 "Horticulture Sciences",
                 "Greenhouse Plant Production & Management"):
        assert name in page, f"the page no longer names {name!r}"
        assert any(name.lower() in t.lower() for t in measured), (
            f"the page names {name!r} as unmatched and the last measured run "
            f"does not have it in that set")


def cache_is_complete() -> bool:
    """Every page the sitemap lists is on disk. Reads no network — the
    sitemap itself is cached."""
    from etl import probe_pwcs as source

    if not (pathlib.Path(__file__).resolve().parents[1] / "data" / "pwcs").exists():
        return False
    try:
        urls = source.catalogue_urls(True)
    except Exception:                      # noqa: BLE001 — no cached sitemap
        return False
    return bool(urls) and all(source.cached_path(u).exists() for u in urls)


@pytest.mark.skipif(
    not cache_is_complete(),
    reason=("the cached catalogue is incomplete — run `python -m etl.probe_pwcs` "
            "first; a partial cache would fetch the remainder from the district"))
@pytest.mark.network  # deliberately live — see the docstring
def test_the_record_still_matches_the_live_sources():
    """The other half: is the RECORD still what the sources say?

    The tests above check the page against a committed measurement, which is
    hermetic and fast and would keep passing forever against a record that has
    gone stale. This re-measures and diffs — so upstream drift surfaces once,
    here, as "the record is stale", rather than as eight lines of hand-edited
    prose on a commit that has nothing to do with it.

    Carries the same skip as every other cache-backed test in this repo:
    `pwcs_source.read()` walks a sitemap and fetches what is missing, which
    from CI means ~960 requests to one school district.
    """
    from etl import new_york_catalog, probe_sced, sced_reach

    ny = new_york_catalog.new_york(probe_sced.fetch(new_york_catalog.NEW_YORK))
    reach = sced_reach.district_reach(ny["titles"], set(ny["state_extensions"]))
    fresh = probe_sced.record(ny, reach)

    drifted = [k for k in fresh["new_york"]
               if fresh["new_york"][k] != RECORD["new_york"].get(k)]
    drifted += [f"district.{k}" for k in fresh["district"]
                if fresh["district"][k] != RECORD["district"].get(k)]

    assert not drifted, (
        f"{drifted} have changed upstream since the record was taken. The "
        f"page quotes these, so refresh with `python -m etl.probe_sced "
        f"--record` and update the prose in one commit — that is what this "
        f"exists to make visible.")
