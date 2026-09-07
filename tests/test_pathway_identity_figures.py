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

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = "docs/sources/pathway-identity.md"
#: "the schema" is two files since #157. Naming one of them in a check is how a
#: guard keeps passing after the sentence it guards moves to the other — the
#: 960-course guard did exactly that, and the NEGATIVE assertions below are the
#: shape where it is silent rather than loud.
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


def read(path: str) -> str:
    if path == SCHEMA:
        return "\n".join(
            f.read_text(encoding="utf-8")
            for f in sorted((ROOT / "schema").glob("*.cypher")))
    return (ROOT / path).read_text(encoding="utf-8")


def stated(path: str, pattern: str):
    """The figure a sentence states, and the sentence, so a failure shows both.

    A pattern that matches nothing is a FAILURE, never a pass — that is the
    vacuous-parse trap this repo has been bitten by: a regex anchored on
    wording returns no match after a harmless reflow, and every assertion
    downstream of it passes on an empty set.
    """
    found = re.search(pattern, read(path))
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
    said, sentence = stated(path, pattern)
    assert said == expected, (
        f"{path} says {said}; the record measured {expected}.\n"
        f"  sentence: {sentence}\n"
        f"Re-run `python -m etl.probe_pathway_identity --record` if the "
        f"Registry changed, then update the prose — or the other way round.")


def test_the_verdict_is_stated_wherever_the_key_is_declared():
    """A decision recorded in one file and not the others is how #85 arose in
    the first place: the schema said `ctid`, the loader wrote `url`."""
    for path in (SCHEMA, "docs/schema.md", DOC):
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
    schema = read(SCHEMA)
    block = schema[schema.index("// Pathway — "):
                   schema.index("CREATE CONSTRAINT ON (pw:Pathway)")]
    assert "LEFT" in block and "rpartition" in block, (
        "the Pathway block must say the id parses from the LEFT and name "
        "Level's rpartition as the wrong rule to copy")


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
    for path in (SCHEMA, "docs/schema.md"):
        assert stale not in read(path), f"{path} still defers the decision"
