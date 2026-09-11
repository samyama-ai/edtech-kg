"""`DATASET-CARD.md` against the runs that produced it — edtech-kg#16.

The card is the document a reader trusts or does not, so every figure on it is
checked against a committed record. A number with no record behind it is a
number somebody typed, which is the failure this repo has had most often.

Nothing here fetches. Eight probes wrote the records; this reads them.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CARD = ROOT / "DATASET-CARD.md"
SOURCES = ROOT / "docs" / "sources"


def card() -> str:
    assert CARD.exists(), "DATASET-CARD.md is missing (#16)"
    return CARD.read_text(encoding="utf-8")


def record(name: str) -> dict:
    path = SOURCES / f"{name}-measured.json"
    assert path.exists(), f"{path.name} is missing, so the card's figures have no run"
    return json.loads(path.read_text(encoding="utf-8"))


def grouped(text: str) -> set[int]:
    """Grouped numbers only. A bare `5` is a count and also half the prose."""
    return {int(m.replace(",", ""))
            for m in re.findall(r"(?<![\d,])(\d{1,3}(?:,\d{3})+)(?![\d,])", text)}


def rounded(text: str) -> set[str]:
    """The ROUNDED figures — the ones `grouped()` cannot see.

    `grouped()` matches comma-separated integers, so "about 157 KB" and
    "imports in 0.02s" were invisible to the guard that exists to stop typed
    figures. Setting `snapshot.bytes` to 999501 and `import.seconds` to 9.87
    left the whole suite green, and the card had ALREADY drifted: it quoted
    0.02s against a record saying 0.03.

    Generalised rather than asserting the two strings, so the next rounded
    figure someone adds is covered by construction.
    """
    return set(re.findall(r"\d+(?:\.\d+)?\s*(?:KB|MB|GB)", text)) | \
        set(re.findall(r"\d+\.\d+s\b", text))


def test_every_rounded_figure_on_the_card_comes_from_a_record():
    """**Both directions**, like the exact-count ban beside it: every rounded
    figure the card prints must be derivable from a record, and the figures
    the records support must be the ones printed."""
    snap = record("snapshot")
    spine = record("national-spine")
    size = f"{round(snap['snapshot']['bytes'] / 1024)} KB"
    imported = f"{snap['import']['seconds']}s"
    loaded = f"{spine['issued']['seconds']}s"
    text = card()

    for figure, why in ((size, "the snapshot's size"),
                        (imported, "its import time"),
                        (loaded, "the spine load time")):
        assert figure in rounded(text), (
            f"the card should carry {figure!r} for {why}; it carries "
            f"{sorted(rounded(text))}")

    # The reverse: nothing rounded on the page that no record supports.
    supported = {size, imported, loaded}
    assert rounded(text) <= supported, (
        f"these rounded figures are on the card and in no record: "
        f"{sorted(rounded(text) - supported)}")


def test_the_records_the_card_rests_on_all_exist():
    """A card built from records that have gone is a card of typed figures."""
    for name in ("education", "licences", "registry-licence", "federal-direct",
                 "state-access", "ceds", "national-spine"):
        assert (SOURCES / f"{name}-measured.json").exists(), name


def test_every_source_count_on_the_card_is_the_measured_one():
    """The source table is the part a reader quotes."""
    text = card()
    for source in record("education")["sources"]:
        assert f"{source['count']:,}" in text, (
            f"the card does not state the measured count for "
            f"{source['source']} ({source['count']:,})")


def test_every_measured_source_appears_on_the_card():
    """The other direction. A source measured and left off the card is one a
    reader cannot know about — and the awkward ones are the tempting omission."""
    text = card()
    for source in record("education")["sources"]:
        assert source["source"] in text, f"{source['source']} is measured and absent"


def test_no_grouped_figure_on_the_card_is_unaccounted_for():
    """Anything a reader could quote has to come from a run."""
    edu, fed, reg, ceds = (record("education"), record("federal-direct"),
                           record("registry-licence"), record("ceds"))
    known = {s["count"] for s in edu["sources"]}
    known |= {fed["ipeds"][k] for k in ("rows", "rows_x_counts", "wrapper_rows",
                                        "awards_first_major")}
    known |= {reg["records"]["envelopes"], ceds["classes"]}
    # The loaded graph. **1,287 is here as a SUPERSEDED figure** — the card
    # names it as the number it used to carry, and #25 measured the graph per
    # type and found 1,417. Kept so the correction can stay on the page.
    known |= {1_098, 1_287, 791}
    # The national spine (#7). Read from the record rather than listed here: a
    # literal would be a second copy of the figure, which is the thing this
    # test exists to prevent, written into the test that prevents it.
    spine = record("national-spine")
    known |= set(spine["in_graph"].values())
    known |= {spine["issued"][k] for k in
              ("statements_issued", "nodes_and_edges_created",
               "already_present", "completions_in",
               "rows_skipped_zero_awards", "duplicate_rows_skipped")}
    known |= {round(spine["issued"]["seconds"])}

    # The snapshot (#25): its size, its import counts, and the /api/status
    # edge figure the card warns against reading. From the record, not typed.
    snap = record("snapshot")
    known |= set(snap["counts"].values())
    known |= {snap["snapshot"]["bytes"],
              sum(snap["counts"][k] for k in
                  ("REQUIRES", "IN_SUBJECT", "INCLUDES", "HAS_REQUIREMENT")),
              # **2,834 was TYPED here**, in the set whose whole job is to
              # catch typed figures, under a comment reading "From the record,
              # not typed" — and the record carried no such field, only a
              # sentence in its `_` note. It is measured now, from both
              # engines, so it comes from the record like everything else.
              snap["edge_count_readings"]["cypher_loaded"]
                  ["api_status_storage"]["edges"],
              snap["edge_count_readings"]["cypher_loaded"]
                  ["per_type"]["undirected_total"]}
    unexplained = grouped(card()) - known
    assert not unexplained, (
        f"these grouped figures are on the card and in no record: "
        f"{sorted(unexplained)}")


def test_the_card_says_the_completions_figure_is_not_people():
    """The largest number on the page and the one most easily misread."""
    text, ip = card(), record("federal-direct")["ipeds"]
    assert f"{ip['awards_first_major']:,}" in text, (
        "the card quotes the row count without the award count")
    assert "rows, not people" in text.lower() or "not people" in text.lower()


def test_the_card_says_what_is_not_loaded_rather_than_leaving_it_blank():
    """#16 asks for this specifically: absent, and SAID to be absent. A blank
    cell reads as zero and zero reads as a measurement."""
    text = card()
    assert "absent, not blank" in text.lower()
    for label in ("Programme", "Occupation", "Institution", "Completion"):
        assert label in text, f"{label} is declared and empty and the card omits it"


def test_the_card_states_the_registry_may_not_be_loaded():
    """The one licence that constrains the design. A card that omits it invites
    exactly the mistake #56 exists to prevent."""
    text = card()
    assert "Credential Registry" in text
    assert re.search(r"Credential Registry data.*\*\*no\*\*", text), (
        "the card does not say plainly that Registry data may not be loaded")


def test_the_card_carries_known_issues_and_they_name_real_gaps():
    text = card()
    assert "## Known issues" in text
    for gap in ("one district", "not loaded", "state education departments"):
        assert gap.lower() in text.lower(), f"known issues omit: {gap}"


def test_the_state_access_figure_agrees_with_the_record_everywhere():
    """It did not. `docs/scope.md` said three of five departments do not answer
    while the source page said four and the record supports four — only Texas
    serves. A figure restated in a second document with nothing tying it back
    is the shape that drifts."""
    departments = record("state-access")["departments"]
    served = [n for n, v in departments.items()
              if v.get("robots_txt", {}).get("outcome") == "served"]
    unanswered = len(departments) - len(served)
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    scope = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    claim = re.search(r"(\w+) of (\w+)\s*\n?state education departments do not answer", scope)
    assert claim, "the scope.md reachability sentence changed shape"
    assert claim.group(1) == words[unanswered], (
        f"scope.md says {claim.group(1)} of {claim.group(2)} departments do not "
        f"answer; the record has {unanswered} of {len(departments)}")


def test_the_spine_the_record_holds_is_actually_on_the_card():
    """**The reverse direction, which was missing.** Every check here ran
    page → record: a figure on the page had to be in a run. Nothing ran
    record → page, so the whole "One state's higher education" section could
    be DELETED and the suite stayed green — mutation-verified.

    CONTRIBUTING names this direction: *a figure in the record that is not on
    the page is a measurement nobody published.*
    """
    spine = record("national-spine")
    text = card()
    assert "higher education" in text, (
        "the card no longer describes the loaded spine at all, and every "
        "other check here would still pass")
    for label, count in spine["in_graph"].items():
        assert f"{count:,}" in text, (
            f"the record holds {label} = {count:,} and the card does not "
            f"carry it")
    assert f"{spine['second_run']['nodes_and_edges_created']:,} created" in text \
        or f"**{spine['second_run']['nodes_and_edges_created']:,}** created" in text, (
        "the idempotence figure is recorded and not published")
