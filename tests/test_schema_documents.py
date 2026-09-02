"""The schema file against the documents that describe it.

`schema/edtech_kg.cypher` and `docs/schema.md` must agree in BOTH directions —
a label in the cypher nobody documented is a label nobody can use, and a label
the doc promises that the ontology does not declare is a promise nothing keeps.
Counts stated in prose are compared as integers against the documents they are
about, because a hand-written figure has gone stale in a shipped file three
times in this repo.

Split from `tests/test_schema_cypher.py` when it passed the 500-line review
limit. Split by SUBJECT, the standard set when that file was first split: this
one reads the documents, and `test_schema_cypher.py` reads only the cypher. The
shared readers are in `tests/schema_source.py`; the tests that need a running
engine are in `tests/test_schema_engine.py`.
"""

import re

from tests.schema_source import (QUESTIONS, SCHEMA, SCHEMA_DOC, edges,
                                 first_column, labels, section)
from tests.spelling import spelled


def test_every_constrained_label_appears_in_the_schema_doc():
    """A label nobody documented is a label nobody can use."""
    documented = SCHEMA_DOC.read_text()
    missing = [label for label in labels() if f"`{label}`" not in documented]
    assert not missing, f"in the cypher but not in docs/schema.md: {missing}"


def test_every_documented_label_exists_in_the_schema():
    """The reverse: the doc must not promise a label the ontology does not
    declare. Both tables in docs/schema.md are label tables."""
    # `section()`, not a raw split: `split(h)[0]` on a renamed heading yields
    # the WHOLE document as the "label table", so `first_column` finds rows
    # from every table on the page and the check passes on the wrong set.
    tables = section(SCHEMA_DOC.read_text(), "# Node labels — tier 1", "## Edge types")
    documented = first_column(tables)
    assert documented, "no label rows found — did the tables change shape?"
    assert documented <= set(labels()), f"documented but not declared: {documented - set(labels())}"


def documented_edges() -> set[str]:
    """The edge table's first column. Two tests sliced and parsed the same
    table independently, so a change had to be made in both places."""
    table = section(SCHEMA_DOC.read_text(), "## Edge types", "## Why these shapes")
    documented = first_column(table)
    assert documented, "no edge rows found — a reflowed table would pass vacuously"
    return documented


def test_the_schema_doc_agrees_with_the_questions_it_claims_to_serve():
    """`docs/schema.md` says "nineteen of the twenty tier-4 questions" — a
    hand-written number about a different document, which is the class of claim
    this repo has had to correct three times."""
    block = section(QUESTIONS.read_text(), "## Tier 4", "## Tier 5")
    questions = re.split(r"\*\*Q\d+", block)[1:]
    answerable = sum(1 for q in questions if "✅" in q)

    # Read the document's own words and compare integers. Predicting how it
    # will spell a number wedges the test: with a digits fallback, a count
    # outside the word map demands the literal digits, so spelling it out —
    # the natural fix, and what both documents do — leaves this failing.
    claim = SCHEMA_DOC.read_text().lower()
    stated = re.search(r"([\w-]+) of the ([\w-]+) tier-4", claim)
    assert stated, "the schema doc no longer states a tier-4 count in that shape"
    assert (spelled(stated.group(1)), spelled(stated.group(2))) == (answerable, len(questions)), (
        f"the schema doc says {stated.group(0)!r}, but questions.md has "
        f"{answerable} answerable of {len(questions)}"
    )


def test_the_competency_gap_count_agrees_with_the_questions():
    """docs/schema.md and the cypher both said six; questions.md says three.
    The schema was drafted before #65 corrected that count, and the stale
    figure shipped in two files — the hand-counted-figure class again, one
    document removed from where it was fixed."""
    block = section(QUESTIONS.read_text(), "## Tier 1", "## The competency gap")
    # Explicit pairing, not `zip(*[iter(...)]*2)`: that drops a trailing
    # element when the split is odd, so the last question on the page could
    # vanish from the count without anything failing.
    parts = re.split(r"\*\*Q(\d+)", block)[1:]
    assert len(parts) % 2 == 0, (
        f"the tier-1 block splits into {len(parts)} pieces, which is odd — the "
        f"question markers and their bodies no longer alternate")
    blocked = [parts[i] for i in range(0, len(parts), 2)
               if "competency" in parts[i + 1].lower()]
    # Anchored on the competency-gap sentence itself. A looser pattern matched
    # an unrelated "those questions was blocked" elsewhere on the page.
    for path, pattern in ((SCHEMA_DOC, r"([\w-]+) questions?[^.]*?blocked on one thing"),
                          (SCHEMA, r"competency gap — ([\w-]+) questions")):
        stated = re.search(pattern, path.read_text().lower())
        assert stated, f"{path.name} no longer states a competency-gap count"
        assert spelled(stated.group(1)) == len(blocked), (
            f"{path.name} says {stated.group(1)!r}, but questions.md blocks "
            f"{len(blocked)}: {blocked}")


def test_what_it_does_not_claim_is_written_down():
    """The house standard: limits stated before anyone finds them."""
    for document in (SCHEMA.read_text(), SCHEMA_DOC.read_text()):
        assert "does not claim" in document.lower()


def test_tier_two_labels_are_marked_as_empty():
    """A modelled-but-unpopulated label read as populated would overstate the
    graph. The doc must say which are which."""
    doc = SCHEMA_DOC.read_text()
    assert "modelled and empty" in doc
    tier_two = section(doc, "modelled and empty", "## Edge types")
    for label in ("Credential", "Level", "Competency", "EarningsRecord"):
        assert f"`{label}`" in tier_two, label

    # `Pathway` is deliberately NOT in that list any more. It was modelled on
    # the Credential Registry and left empty; a district publishes pathways as
    # pages and 38 of them load, so it is tier 1 keyed on `url`. Asserted in
    # both directions, because a label that drifts back into tier 2 while the
    # loader keeps writing it would be a table saying "empty" about 38 nodes.
    assert "`Pathway`" not in tier_two, "Pathway is populated; it is not tier 2"
    tier_one = section(doc, "## Node labels — tier 1", "## Node labels — tier 2")
    assert "`Pathway`" in tier_one, "Pathway is loaded but appears in neither tier"


def test_the_limits_of_the_merge_rule_are_admitted():
    """1.1.0 does not reject a duplicate CREATE, so "loaders must MERGE" is a
    rule with no enforcement behind it. One loader is now checked against this
    file by a test; the engine still checks nothing, and the document has to
    keep saying which of those two is true.

    Matched on the CLAIM, not on one sentence. An earlier version pinned exact
    words, so moving the paragraph out of the numbered scope list — where it
    did not belong, being about loaders rather than about scope — broke a test
    that has no opinion about where the paragraph sits.
    """
    text = SCHEMA_DOC.read_text()
    flat = " ".join(text.split()).lower()
    assert "merge rule is enforced for one loader" in flat, \
        "the doc no longer says which of the loader and the engine enforces it"
    assert "does not reject a duplicate create" in flat, \
        "the reason the rule matters — 1.1.0 accepts a duplicate CREATE — is gone"
    assert "etl/loader.py is still the repo template" not in text, \
        "the doc still describes the state before etl/load_pwcs.py existed"


def test_no_document_calls_960_a_course_count():
    """The tier-1 correction says the course count is 791; a later section still
    said "one district, 960 courses". A page that corrects itself in one place
    and repeats the error in another is worse than one that never corrected it.

    Both files, not just the doc. The guard used to read `docs/schema.md`
    alone, and the same wrong figure was sitting in the cypher's own "what this
    does NOT claim" section — the stale-figure-one-file-over class this repo
    has now corrected three times.
    """
    for path in (SCHEMA_DOC, SCHEMA):
        flat = " ".join(path.read_text(errors="replace").split())
        assert "960 courses" not in flat, (
            f"{path.name} still calls 960 a course count; it is the sitemap "
            f"page count, and the course count is 791")


def test_the_classification_hole_says_it_was_fixed_not_that_it_stands():
    """`docs/schema.md` opens its holes list with "written down before anyone
    finds it". One of those holes recorded that four pages loaded as courses
    and 172 rows never became edges — true until edtech-kg#87, misleading after.

    A page that states its own limits is only worth reading if the statement
    keeps up with what is known, in both directions: a hole that closes has to
    stop reading as open.

    Targeted at the classification section by its own heading, not by the range
    the holes list occupies. It used to read the holes range and pass because
    this section happens to sit inside it — which would have kept passing if
    the section were moved anywhere else in the file, and stopped passing if
    the holes list gained a later heading. Neither has anything to do with what
    this is checking.
    """
    doc = SCHEMA_DOC.read_text()
    heading = "## A page is classified by what it publishes, not only by its URL"
    assert heading in doc, (
        "the classification section is gone — #87's finding is no longer "
        "recorded anywhere on the page")
    body = section(doc, heading, "## Verified against")
    assert "Fixed in edtech-kg#87" in body, (
        "the classification section still reads as an open gap; #87 closed it")
    assert "is short by 172" not in body, (
        "the doc still says INCLUDES is short by 172 edges")

    includes_row = [line for line in doc.splitlines()
                    if line.startswith("| `INCLUDES`")]
    assert includes_row, "the INCLUDES row moved"
    assert "316 edges" in includes_row[0], (
        "the INCLUDES row still quotes the pre-#87 edge count")


def test_every_documented_edge_exists_in_the_schema():
    documented = documented_edges()
    assert documented <= edges(), f"documented but not in the cypher: {documented - edges()}"


def test_every_edge_in_the_schema_is_documented():
    """The reverse direction, which labels already had and edges did not: an
    edge added to the cypher and never written down would not have failed.

    Only the first column counts. Collecting every backticked word in the table
    picks up the node labels in the From/To column too, so an edge sharing a
    name with a label would pass without being documented."""
    documented = documented_edges()
    missing = sorted(edges() - documented)
    assert not missing, f"in the cypher but not in docs/schema.md: {missing}"


def test_the_includes_arithmetic_in_the_schema_doc_closes():
    """The INCLUDES row gives five numbers. A reader adding them up has to get
    the answer the row states, or the row is teaching a wrong figure.

    It did not close on the first attempt, and the way it failed is the point:
    the row said "316 edges from 374 published rows" and then "a further 16
    rows resolve against no loaded course", which reads as either 374 − 58 −
    16 = 300 or 374 − 58 = 316 depending on whether the 16 are inside the 374
    or beside them. They are beside them. Prose that supports two readings and
    only one arithmetic is the same defect as a wrong number.

    Read out of the document rather than asserted here, so the test fails when
    the page changes rather than when this file does.
    """
    row = _includes_row()
    published = _figure(row, r"publish \*\*([\d,]+) rows\*\*")
    resolving = _figure(row, r"([\d,]+) resolve to a loaded course")
    unresolved = _figure(row, r"\*\*([\d,]+) resolve to none\*\*")
    repeats = _figure(row, r"\*\*([\d,]+) repeat a pathway-course pair")
    edges = _figure(row, r"([\d,]+) − [\d,]+ = ([\d,]+) edges", group=2)

    assert resolving + unresolved == published, (
        f"{resolving} resolving + {unresolved} unresolved = "
        f"{resolving + unresolved}, but the row says {published} rows")
    assert resolving - repeats == edges, (
        f"{resolving} − {repeats} = {resolving - repeats}, "
        f"but the row says {edges} edges")


def test_the_hole_seven_arithmetic_closes_too():
    """`185 → 316` is a claim about what the fix recovered, and the review
    could not check it from what the page said. It now states the breakdown,
    so the +131 is arithmetic rather than assertion."""
    text = " ".join(SCHEMA_DOC.read_text(errors="replace").split())
    hole = text[text.index("The four pages publish"):]
    hole = hole[:hole.index("The node total is unchanged")]

    rows = _figure(hole, r"publish \*\*([\d,]+) rows\*\*")
    resolving = _figure(hole, r"([\d,]+) resolve to a loaded course")
    unresolved = _figure(hole, r"([\d,]+) resolve to none")
    repeats = _figure(hole, r"\*\*([\d,]+) repeat a pair already")
    gained = _figure(hole, r"= ([\d,]+) new edges")
    before = _figure(hole, r"\*\*([\d,]+) \+ [\d,]+ = [\d,]+\*\*")
    after = _figure(hole, r"\*\*[\d,]+ \+ [\d,]+ = ([\d,]+)\*\*")

    assert resolving + unresolved == rows, f"{resolving}+{unresolved} != {rows}"
    assert resolving - repeats == gained, f"{resolving}-{repeats} != {gained}"
    assert before + gained == after, f"{before}+{gained} != {after}"


def _includes_row() -> str:
    for line in SCHEMA_DOC.read_text(errors="replace").splitlines():
        if line.startswith("| `INCLUDES`"):
            return line
    raise AssertionError("no INCLUDES row in the edge table")


def _figure(text: str, pattern: str, group: int = 1) -> int:
    """One number out of the page, or a failure naming what was looked for.

    Failing rather than returning None matters: a regex that stops matching
    because the sentence was reworded would otherwise make the arithmetic test
    pass on nothing at all, which is the vacuous pass this suite keeps finding.
    """
    import re
    found = re.search(pattern, text)
    assert found, f"no figure matching {pattern!r} — the wording changed"
    return int(found.group(group).replace(",", ""))


#: What `docs/schema.md` offers as examples of what `REQUIRES` makes
#: answerable, and the tier-4 question each one names. An exemplar is a claim
#: about a question, and the guard beside it only checked the COUNT — so the
#: count was updated when the tier was re-marked and the words were not, which
#: left "cycle detection" listed as answerable while Q71 is ❌ for it.
REQUIRES_EXEMPLARS = {
    "blast radius": "Q61",
    "shortest path": "Q72",
    "reachability": "Q77",
    "ancestor and descendant sets": "Q69",
}

#: Named because the prose names it, and it must stay named: the sentence says
#: NOT cycle detection, and the day Q71 becomes answerable that sentence is
#: wrong in the other direction.
NOT_AN_EXEMPLAR = {"cycle detection": "Q71"}


def test_the_schema_doc_only_offers_examples_the_questions_agree_with():
    """A figure restated in a second document with nothing tying it to the
    first is this repo's most common finding. This is the words half of one."""
    from tests.questions_document import marks

    status = marks()
    prose = SCHEMA_DOC.read_text(encoding="utf-8")
    sentence = [line for line in prose.splitlines() if "tier-4 questions answerable" in line]
    assert sentence, "the REQUIRES paragraph in docs/schema.md has moved or been reworded"
    # WHITESPACE-NORMALISED. The prose is wrapped, so `shortest path` sits
    # across a line break and a literal match reported it as removed — a guard
    # that fails on a reflow is a guard someone deletes.
    paragraph = " ".join(
        prose.split("Prerequisite chains are the reason", 1)[1][:700].split())

    for phrase, question in REQUIRES_EXEMPLARS.items():
        assert phrase in paragraph, f"{phrase!r} is no longer offered as an example"
        assert status[question] != "no", (
            f"docs/schema.md offers {phrase!r} as answerable and {question} is "
            f"marked ❌ — the count was updated and the examples were not")

    for phrase, question in NOT_AN_EXEMPLAR.items():
        assert status[question] == "no", (
            f"{question} is no longer ❌, so docs/schema.md saying it is NOT "
            f"{phrase!r} has gone stale in the other direction")
        assert f"NOT {phrase}" in paragraph, (
            f"docs/schema.md no longer says {phrase!r} is excluded, and "
            f"{question} is still ❌ for it")

