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

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPRENTICESHIP = Path(__file__).resolve().parents[1] / "docs" / "sources" / "apprenticeship.md"
CAREERONESTOP = Path(__file__).resolve().parents[1] / "docs" / "sources" / "careeronestop.md"


def flat(path) -> str:
    """A page as one line, with whitespace normalised and emphasis stripped.

    Every text assertion in this file runs against this, because both of the
    ways a sentence changes shape defeated them:

    A phrase that WRAPS does not contain the newline, so `"reachable no other
    way" not in page` passed the moment the sentence happened to wrap.

    A phrase that gains **emphasis** no longer matches either — `63 of them`
    becomes `**63** of them`, and a negative assertion goes quiet while the
    claim it bans is on the page in bold. Caught by mutation: re-adding the
    false claim, wrapped and bolded, passed a run that flattening alone had
    already fixed.

    Both are negative assertions that stop guarding without failing, which is
    the shape of every defect this file exists to catch.
    """
    return " ".join(path.read_text(encoding="utf-8").split())


def plain(path) -> str:
    """`flat`, with emphasis stripped as well.

    For the NEGATIVE assertions only. A pin asserts the page marks a figure as
    measured, so `**449**` must keep its markers; a ban asserts a claim is not
    made, so the markers must not be able to hide it. Two different questions,
    and one helper answering both broke the pins.
    """
    return " ".join(
        path.read_text(encoding="utf-8").replace("*", "").replace("`", "").split())


def test_the_documents_quote_only_figures_the_probe_produces():
    """Every figure on both pages comes from the probe. These are the ones the
    argument rests on, so a changed figure fails here rather than being quoted
    for another month."""
    page = flat(APPRENTICESHIP)
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
    page = flat(APPRENTICESHIP).lower()
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
    page = flat(APPRENTICESHIP)
    page = " ".join(page.split())
    for host in ("onetcenter.org", "nces.ed.gov", "careertech.org"):
        assert f"control: `{host}`" in page, (
            f"{host} is cited as a control but is not in the measured table")


def test_the_careeronestop_page_states_what_it_cannot_establish():
    """A blocked source is easy to overclaim. The page must keep saying that a
    refused connection from one network is not proof the source is down."""
    page = flat(CAREERONESTOP).lower()
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
    # The FALSE form, not the phrase. "reachable no other way" also appears
    # in the correction — "0 of them are reachable no other way" — so banning
    # the words alone bans the fix as well. What must not come back is the
    # claim attached to the 63.
    page = plain(APPRENTICESHIP)
    # The PROBE'S OWN prose too, not only the pages. Both claims this test
    # bans survived in `etl/probe_apprenticeship.py`'s module docstring for a
    # full round — the retracted "what this graph cannot see", and the
    # citation to a licensure question `docs/questions.md` does not contain.
    # Fixing the documents and not the code that generates them is the same
    # partial sweep the documents were fixed for.
    prose = page + " " + " ".join(
        (ROOT / "etl" / "probe_apprenticeship.py").read_text(
            encoding="utf-8").replace("*", "").replace("`", "").split())

    for claim in ("63 of them are reachable no other way",
                  "this graph has no shape for those",
                  "what this graph cannot currently see",
                  "cannot see a public, funded route into any of them",
                  "licensure question docs/questions.md marks unanswerable"):
        assert claim not in prose, (
            f"{claim!r} appears in a page or in the probe's own docstring; "
            f"every occupation in that set is a code this repo's crosswalk "
            f"carries, which the probe prints as `apprenticeship SOC not in "
            f"ours: 0` in the same run")

    assert "0 of them are reachable no other way" in page, (
        "the page no longer states the corrected answer to #39")
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
    # RAW lines: this one parses a markdown table, so flattening the page
    # would leave it nothing to parse.
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
    # ONE phrase. This was `"disagree by 63 occupations" in page or
    # "63 occupations" in page` — the second is a substring of the first, so
    # the first disjunct could never decide the result and the assertion was
    # the looser one wearing the stricter one's name.
    assert "63 occupations" in page, (
        "the page's prose no longer names the figure its table totals")


def test_every_question_the_page_names_is_quoted_as_the_file_has_it():
    """It cited a line that does not exist.

    edtech-kg#38 quotes Q23 as marked unanswerable, "state-by-state and not
    centrally published". `docs/questions.md` reads *Which colleges near me
    offer this programme?* — marked answered — and the phrase appears nowhere
    in `docs/`. The page repeated the issue's wording as a citation.

    **The first version of this guard asserted nothing.** It scanned quoted
    phrases and kept only those within 400 characters of a `docs/questions.md`
    mention — a condition nothing on the page met, so the loop ran zero times
    and the test passed by examining no quotes at all. A guard added to catch
    a fabricated citation, itself proving nothing.

    Driven off the Q-NUMBERS instead, which is what the defect was about: for
    every `Q<n>` this page names, the file must have that question and the
    page must quote its actual text. That cannot go vacuous — if the page
    names no questions, there is nothing to check and this says so.
    """
    named = sorted(set(re.findall(r"\bQ(\d+)\b", plain(CAREERONESTOP))), key=int)
    assert named, (
        "the page names no question at all, so this check read nothing — "
        "which is how its first version passed")

    questions = (ROOT / "docs" / "questions.md").read_text(encoding="utf-8")
    page = plain(CAREERONESTOP).lower()

    for number in named:
        found = re.search(rf"\*\*Q{number}\.\*\*\s*(.+)", questions)
        assert found, (
            f"the page discusses Q{number} and docs/questions.md has no such "
            f"question — the citation is to a line that does not exist")
        # The question text, without the status marker the file ends it with.
        stem = re.sub(r"\s*[✅⚠❌⬜].*$", "", found.group(1)).strip()
        assert stem.lower()[:40] in page, (
            f"the page names Q{number} without quoting what it says. The file "
            f"has {stem!r}, and a page that names a question and characterises "
            f"it differently is the defect this exists to catch.")


def test_the_page_does_not_claim_what_it_says_it_cannot_tell():
    """It said the probe "cannot tell which… so this page does not claim which"
    and then named a specific failure mode three more times.

    I fixed one phrasing with a literal replace and left three others, so the
    page ended up asserting the caveat AND contradicting it. The sweep is for
    the CLAIM, not for the sentence I happened to edit — which is the same
    mistake as fixing one of two pages that feed a conclusion.

    `no connection (timed out)` is what the probe records. Anything naming a
    mechanism it cannot distinguish is a claim it did not measure.
    """
    page = plain(CAREERONESTOP)

    for mechanism in ("refused TCP", "refused connection", "TCP connection",
                      "connection refused", "does not complete a TLS"):
        assert mechanism.lower() not in page.lower(), (
            f"the page names {mechanism!r} as the failure mode, and the probe "
            f"records only `no connection (timed out)` — it cannot tell a TLS "
            f"handshake from a dropped or filtered connection, and the page "
            f"says so elsewhere")

    assert "times out" in page, "the page no longer says what was measured"


def test_no_resolved_address_is_typed_into_the_page():
    """A hardcoded IP goes stale silently.

    DNS is a fact about the day of the run, and the probe already prints the
    address. Typing it here makes the page wrong the next time the host moves,
    with nothing to say so — on a page whose first line is that nothing on it
    is typed.
    """
    from etl import probe_apprenticeship as probe

    # The PUBLIC RESOLVERS are exempt. Naming which resolvers were asked is
    # the method — it is what makes "resolves nowhere" a claim rather than an
    # observation from one network — and those addresses are constants in the
    # probe, not results from a run.
    method = {address for _, address in probe.PUBLIC_RESOLVERS}
    page = flat(CAREERONESTOP)
    typed = [a for a in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", page)
             if a not in method]
    assert not typed, (
        f"the page carries the resolved address(es) {typed}. Those come from "
        f"DNS on the day of the run and are in the probe output already.")
