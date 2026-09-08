"""The pathway-key verdict, held to the measurement it rests on.

#85 is decided by four numbers — 98/98 for `ctid`, and 78 present / 71 distinct
/ 7 lost for `subjectWebpage`. Those numbers are quoted in four places: the
schema's Pathway block, `docs/schema.md`, `docs/ontology-reuse.md` and
`docs/sources/pathway-identity.md`. That is the shape this repo's most common
review finding takes — one figure written in five places, changed in one.

The record is `docs/sources/pathway-identity-measured.json`, written by
`python -m etl.probe_pathway_identity --record`. Nothing here reaches the
network.
"""

import json
import pathlib
import re

import pytest

from tests.schema_source import SCHEMA_FILES, sole_file_stating

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = "docs/sources/pathway-identity.md"
#: "the schema" is two files since #157. Naming one of them in a check is how a
#: guard keeps passing after the sentence it guards moves to the other — the
#: 960-course guard did exactly that, and the NEGATIVE assertions below are the
#: shape where it is silent rather than loud.
#:
#: This was a `sorted(schema/*.cypher)` glob joined into one string, which had
#: three problems the join hid. The glob was a fifth independent definition of
#: "the schema" and agreed with the other four only by luck; an empty or
#: renamed `schema/` made it `""`, so the NEGATIVE tests passed on having read
#: nothing; and every failure message said `schema/*.cypher` rather than the
#: file to go and open. Each schema file is now read and asserted on its own.
SCHEMA = "schema/*.cypher"


RECORD = json.loads((ROOT / "docs" / "sources"
                     / "pathway-identity-measured.json").read_text("utf-8"))

CTID = RECORD["candidates"]["ceterms:ctid"]
WEB = RECORD["candidates"]["ceterms:subjectWebpage"]

#: (file, expected value, pattern capturing the figure out of its sentence).
#: Anchored on enough surrounding words that a reword fails loudly instead of
#: matching some other number further down the file.
QUOTATIONS = [
    (DOC, RECORD["pathways"], r"reads all (\d+) published pathways"),
    (DOC, WEB["absent"], r"\*\*(?:Twenty|(\d+)) pathways publish no webpage"),
    (DOC, WEB["collides"], r"\*\*(?:Seven|(\d+)) more would be silently"),
    (DOC, RECORD["webpage_hosts"]["distinct"],
     r"published across (\d+) hosts"),
    (DOC, WEB["present"], r"\| \*\*(\d+) / 98\*\* \| 71 \|"),
    (DOC, WEB["distinct"], r"\| \*\*78 / 98\*\* \| (\d+) \|"),
    (DOC, WEB["shared_values"], r"\*\*(?:Four|(\d+)) pages are each published"),
    (DOC, CTID["present"], r"\| \*\*(\d+) / 98\*\* \| 98 \| 0 \|"),

    (SCHEMA, RECORD["pathways"],
     r"argued: all (\d+)\n// Registry pathways read"),
    (SCHEMA, WEB["absent"],
     r"`subjectWebpage` leaves (\d+) nulls"),
    (SCHEMA, WEB["collides"],
     r"AND merges (\d+) onto \d+ shared pages"),
    (SCHEMA, WEB["shared_values"],
     r"merges \d+ onto (\d+) shared pages"),

    ("docs/schema.md", RECORD["pathways"],
     r"reads all (\d+)\npublished Registry pathways"),
    ("docs/schema.md", WEB["absent"],
     r"(?:Twenty|(\d+)) Registry pathways publish no webpage"),
    ("docs/schema.md", WEB["collides"],
     r"and seven more|and (\d+) more would be \*silently merged\*"),

    ("docs/ontology-reuse.md", CTID["present"],
     r"`ctid`, which (\d+)/\d+ published pathways carry"),
]

#: Figures that are written out as words rather than digits, so the patterns
#: above capture nothing. Each is checked against the record by name instead —
#: a spelled figure that nothing checks is the same stale-figure risk with the
#: capture group silently returning None.
SPELLED = {"Twenty": 20, "Seven": 7, "seven": 7, "Four": 4}


def sources(path: str) -> list[tuple[str, str]]:
    """(name, text) for each file `path` names — one for a doc, N for SCHEMA.

    Every check below runs against each of these separately. Joining them was
    what turned "the schema states X" into "one of the schema files states X",
    and what let a failure report `schema/*.cypher` instead of a filename.
    """
    if path == SCHEMA:
        return [(f"schema/{f.name}", f.read_text(encoding="utf-8"))
                for f in SCHEMA_FILES]
    return [(path, (ROOT / path).read_text(encoding="utf-8"))]


def declaring_file() -> str:
    """The schema file that declares the Pathway key, as `schema/<name>`.

    **The four schema-sourced rows below belong to THIS file, not to whichever
    schema file happens to quote them.** Before the split they were pinned to
    `schema/edtech_kg.cypher`; the fan-out over both files replaced that with
    "some schema file says it", which is strictly weaker.

    Measured on this branch: moving the "all 98 Registry pathways" block out
    of tier 1 and appending it to tier 2 — so the measured reasoning for the
    Pathway key sat in a tier declaring no Pathway — left the suite at 1,383
    passed and nothing noticed.

    `test_the_verdict_is_stated_wherever_the_key_is_declared` was rewritten to
    stop asking the weaker question. Leaving this one asking it put both
    policies in one module.
    """
    declaring = sole_file_stating("CREATE CONSTRAINT ON (pw:Pathway)",
                                  "the Pathway key")
    return f"schema/{declaring.name}"


def read(path: str) -> str:
    """One named document. Deliberately refuses SCHEMA — see `sources`."""
    assert path != SCHEMA, "read one schema file at a time; use sources()"
    return (ROOT / path).read_text(encoding="utf-8")


def stated(path: str, pattern: str, text: str | None = None):
    """The figure a sentence states, and the sentence, so a failure shows both.

    A pattern that matches nothing is a FAILURE, never a pass — that is the
    vacuous-parse trap this repo has been bitten by: a regex anchored on
    wording returns no match after a harmless reflow, and every assertion
    downstream of it passes on an empty set.
    """
    found = re.search(pattern, read(path) if text is None else text)
    assert found, f"{path} no longer states this — pattern {pattern!r} matched nothing"
    digits = next((g for g in found.groups() if g), None)
    if digits is None:
        # The figure is spelled. Read the spelling off the match rather than
        # predicting it: `tests/spelling.py`'s rule is that a document's
        # spelling is read to an int, never an int predicted to a spelling.
        word = next((w for w in SPELLED if w in found.group(0)), None)
        assert word, f"{path}: matched {found.group(0)!r} with no figure in it"
        return SPELLED[word], found.group(0)
    return int(digits), found.group(0)


@pytest.mark.parametrize(
    "path, expected, pattern", QUOTATIONS,
    ids=[f"{p.split('/')[-1]}-{e}" for p, e, _ in QUOTATIONS])
def test_a_quoted_figure_matches_the_record(path, expected, pattern):
    # For SCHEMA, the figure must be in the file that DECLARES the Pathway
    # key — the reasoning has to sit with the constraint it justifies. For a
    # document, the document itself.
    wanted = declaring_file() if path == SCHEMA else path
    quoting = [(name, text) for name, text in sources(path)
               if re.search(pattern, text)]
    assert quoting, (
        f"no file behind {path} states this — pattern {pattern!r} matched "
        f"nothing in {', '.join(n for n, _ in sources(path))}")
    assert [n for n, _ in quoting] == [wanted], (
        f"{pattern!r} is stated in {[n for n, _ in quoting]}; it belongs in "
        f"{wanted}, the file that declares the key this figure decides. A "
        f"figure that drifts into a tier declaring no Pathway is the stale-"
        f"figure risk this module exists for.")
    for name, text in quoting:
        said, sentence = stated(name, pattern, text)
        _matches(name, said, expected, sentence)


def _matches(path, said, expected, sentence):
    assert said == expected, (
        f"{path} says {said}; the record measured {expected}.\n"
        f"  sentence: {sentence}\n"
        f"Re-run `python -m etl.probe_pathway_identity --record` if the "
        f"Registry changed, then update the prose — or the other way round.")


def test_the_verdict_is_stated_wherever_the_key_is_declared():
    """A decision recorded in one file and not the others is how #85 arose in
    the first place: the schema said `ctid`, the loader wrote `url`.

    "Wherever the key is DECLARED" is the schema file carrying the Pathway
    constraint, not either schema file. The joined read asked the weaker
    question — whether one of the two mentioned it — and would have passed with
    the verdict in tier 2 and the constraint it explains in tier 1.
    """
    declares = sole_file_stating("CREATE CONSTRAINT ON (pw:Pathway)",
                                 "the Pathway key")
    for path in (f"schema/{declares.name}", "docs/schema.md", DOC):
        text = read(path)
        assert '"<space>|<identifier>"' in text or \
               '`Pathway.id = "<space>|<identifier>"`' in text, \
            f"{path} does not state the composite key the verdict chose"


def test_the_parse_direction_is_stated_with_the_key_not_only_in_the_doc():
    """The rule that is easiest to get wrong by copying the sibling label.

    `Level` splits from the RIGHT. This splits from the LEFT. Whoever writes
    the first loader reads the schema, so the warning has to be there and not
    only in a source document they may never open.
    """
    # Both anchors out of the one file that carries them. Sliced across the
    # join, a `// Pathway — ` heading in the other tier would silently make
    # this block span a file boundary.
    heading = sole_file_stating("// Pathway — ", "the Pathway heading")
    declares = sole_file_stating("CREATE CONSTRAINT ON (pw:Pathway)",
                                 "the Pathway key")
    assert heading == declares, (
        f"the Pathway commentary is in {heading.name} and the constraint it "
        f"explains is in {declares.name}")
    schema = heading.read_text(encoding="utf-8")
    block = schema[schema.index("// Pathway — "):
                   schema.index("CREATE CONSTRAINT ON (pw:Pathway)")]
    assert "LEFT" in block and "rpartition" in block, (
        f"{heading.name}: the Pathway block must say the id parses from the "
        f"LEFT and name Level's rpartition as the wrong rule to copy")


def test_the_case_the_verdict_does_not_settle_is_stated_as_unsettled():
    """A limit that is only in a commit message is a limit nobody reads.

    The same pathway published by both publishers gets TWO nodes. If that ever
    quietly becomes a claim of deduplication, this fails.
    """
    doc = read(DOC)
    assert "**no, and deliberately" in doc, (
        "the doc must still record that two publishers describing one pathway "
        "produce two nodes, and that this is deliberate")


def test_no_document_still_claims_the_key_question_is_undecided():
    """#85's own words, which three files carried before it was answered."""
    stale = "not a decision\nto take on one publisher's evidence"
    # Each schema file on its own, so the failure names the file. A plain
    # loop: the first version asserted inside a comprehension via a helper
    # that always returned False, so the count below held by construction and
    # said nothing. The vacuous case it was written against — a renamed
    # `schema/` yielding "" — cannot reach here either, because a per-file
    # read raises FileNotFoundError, which is already loud.
    checked = []
    for path in (SCHEMA, "docs/schema.md"):
        for name, text in sources(path):
            assert stale not in text, f"{name} still defers the decision"
            checked.append(name)
    assert len(checked) == len(SCHEMA_FILES) + 1, checked
