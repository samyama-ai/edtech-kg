"""What the two apprenticeship pages CLAIM, against what the probe measures.

Split out of `tests/test_probe_apprenticeship.py` when it passed the 500-line
review limit, and split by subject rather than at a line count. Everything here
reads a published document and checks a sentence in it against a figure the
probe prints. Nothing here drives the probe's parsing; that stays next door.

The split earns itself: every blocker this page has had was a claim the code
did not support rather than a bug. The headline said 63 occupations were
"reachable no other way" and "this graph has no shape for those", while the
probe printed `apprenticeship SOC not in ours: 0` eight lines further down —
both numbers in one run, contradicting each other, and no test looking at the
sentence between them.
"""

from __future__ import annotations

from pathlib import Path

APPRENTICESHIP = Path(__file__).resolve().parents[1] / "docs" / "sources" / "apprenticeship.md"
CAREERONESTOP = Path(__file__).resolve().parents[1] / "docs" / "sources" / "careeronestop.md"


def test_the_documents_quote_only_figures_the_probe_produces():
    """Every figure on both pages comes from the probe. These are the ones the
    argument rests on, so a changed figure fails here rather than being quoted
    for another month."""
    page = APPRENTICESHIP.read_text(encoding="utf-8")
    for claim in ("1,439", "1,171", "**449**", "**419**", "**688**", "**356**",
                  "**63**", "**867**", "**0** of 449"):
        assert claim in page, f"apprenticeship.md no longer states {claim!r}"

    blocked = CAREERONESTOP.read_text(encoding="utf-8")
    assert "**403**" in blocked
    assert "**no connection**" in blocked


def test_the_apprenticeship_page_does_not_claim_the_trades_are_the_gap():
    """The half of the finding that contradicts the issue. edtech-kg#39 assumes
    the exclusive occupations are well-paid trades; measured, construction and
    maintenance are 82% and 91% already reachable through a programme, and the
    gap is in Production. A page that lost that would be quoting a true number
    under a false story."""
    page = APPRENTICESHIP.read_text(encoding="utf-8").lower()
    assert "not the trades" in page, (
        "the page no longer says the gap is not in the trades")
    assert "production" in page, "the page no longer names where the gap is"


def test_both_pages_state_that_these_are_head_requests():
    """A 403 or 405 to HEAD is not evidence about GET, and both pages are
    entirely about telling failure modes apart. The limit belongs on the page
    rather than in the reader's assumptions."""
    for doc in (APPRENTICESHIP, CAREERONESTOP):
        # Whitespace-normalised before matching. These files wrap at 80
        # columns, so a phrase that crosses a line break does not appear as a
        # literal substring — the first version of this test failed on prose
        # that said exactly the right thing, which is a test brittle about
        # formatting rather than about meaning.
        page = " ".join(doc.read_text(encoding="utf-8").split())
        assert "HEAD" in page, f"{doc.name} no longer states the request method"
        assert "not evidence about GET" in page, (
            f"{doc.name} no longer states what a HEAD result does not prove")


def test_the_apprenticeship_page_names_its_control_hosts():
    """Both pages argue the failures are not a general egress problem. That
    argument is only reproducible if the controls are in the run, so the table
    has to carry them."""
    page = APPRENTICESHIP.read_text(encoding="utf-8")
    page = " ".join(page.split())
    for host in ("onetcenter.org", "nces.ed.gov", "careertech.org"):
        assert f"control: `{host}`" in page, (
            f"{host} is cited as a control but is not in the measured table")


def test_the_careeronestop_page_states_what_it_cannot_establish():
    """A blocked source is easy to overclaim. The page must keep saying that a
    refused connection from one network is not proof the source is down."""
    page = CAREERONESTOP.read_text(encoding="utf-8").lower()
    assert "not established" in page
    assert "not cleared" in page, "the verdict is gone"
    assert "registered api key" in page, (
        "the page no longer says what reopening this needs")


def test_the_page_does_not_claim_the_gap_is_one_this_graph_cannot_see():
    """The published claim, pinned to the measurement that contradicts it.

    A reader is told what the number means, and what it means depends on which
    CIP-to-SOC file it was measured against. If the page ever again says the
    exclusive set is invisible to this graph, this fails — because the probe
    says the opposite in the same run.
    """
    page = APPRENTICESHIP.read_text(encoding="utf-8")

    for claim in ("reachable no other way",
                  "this graph has no shape for those",
                  "cannot see a public, funded route into any of them"):
        assert claim not in page, (
            f"the page claims {claim!r}; every occupation in that set is a "
            f"code this repo's crosswalk carries, which the probe prints as "
            f"`apprenticeship SOC not in ours: 0` in the same run")

    assert "disagree" in page.lower(), (
        "the page no longer says what the exclusive count actually measures — "
        "a disagreement between two published crosswalks")


def test_the_major_group_table_adds_up_to_the_headline():
    """The check a reader performs and no test did.

    The table shipped four rows summing to 48 under a headline of 63, with
    nothing on the page saying the other fifteen existed — while the paragraph
    above it argued that the split was computed rather than asserted precisely
    so the claim could be re-run.

    Adding a column up needs no probe and no network, which is what makes the
    absence of this check the surprising part: the page carries both numbers
    and they disagreed.
    """
    page = APPRENTICESHIP.read_text(encoding="utf-8")

    rows, total = [], None
    for line in page.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or not cells[0]:
            continue
        only = cells[3].strip("*").strip()
        if not only.isdigit():
            continue
        if cells[0].strip("*").lower() == "total":
            total = int(only)
        else:
            rows.append(int(only))

    assert rows, "no major-group rows parsed — this check read nothing"
    assert total is not None, (
        "the major-group table has no Total row, so a reader cannot tell a "
        "complete table from a truncated one")
    assert sum(rows) == total, (
        f"the table's own rows sum to {sum(rows)} and it claims {total}; "
        f"{total - sum(rows)} occupations are unaccounted for and nothing on "
        f"the page says so")


def test_the_headline_and_the_table_state_the_same_number():
    """The two halves of the finding, pinned to each other.

    The table's total and the figure the prose leads with are the same
    measurement. They were written at different times against different
    crosswalks once already.
    """
    page = APPRENTICESHIP.read_text(encoding="utf-8")
    assert "| **Total** | | | **63** | |" in page, (
        "the table's total is no longer 63; the prose above it still says 63")
    assert "disagree by 63 occupations" in page or "63 occupations" in page, (
        "the page's prose no longer names the figure its table totals")
