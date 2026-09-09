"""What "the schema" IS — the declared file list, and that every tier is applied.

Named for the declaration, not for a count. It was `test_schema_is_two_files`,
which baked into a filename the very assumption
`test_the_declared_schema_is_every_schema_file` exists to stop anyone relying
on — and a third tier is meant to be an ordinary thing to add.

Split from `tests/test_schema_cypher.py` when it passed the 500-line review
limit. Split by SUBJECT, not by length: everything there asserts what the
schema SAYS — labels, keys, wrapping, sections. These two assert what the
schema is made OF, which is a different failure with a different history.

That history is #157. Splitting one 499-line file in two introduced a class of
bug the single file could not have: a reader that names one file and reports on
"the schema". It has now been closed twice. First for the readers — a tier
going unapplied. Then for the LIST — "the schema" had quietly acquired five
independent definitions, and adding a third tier file left the suite green
while the loader never applied it.

It also holds the tests for LOCATING a declaration — `constraint_line` and
`declaration_site`. Those answer "which file declares this label", which is
the same question as "what is the schema made of", one label at a time.

Nothing here reaches an engine.
"""

from __future__ import annotations

import re

from etl.cypher_script import split_statements, strip_comment
from etl import cypher_script
from tests import schema_source
import pytest

from tests.schema_source import (ROOT, SCHEMA_FILES, constraint_line,
                                 declaration_site, schema_text)


def test_the_declared_schema_is_every_schema_file():
    """A `.cypher` file in `schema/` that nothing declares must fail here.

    `test_both_tiers_are_actually_read` below closed #157's drift for the two
    files that existed when it was written, and the drift then moved rather
    than closing: "the schema" acquired FIVE independent definitions — the
    loader tuple, a copy in `tests/schema_source`, a hand-rolled copy in
    `tests/test_load_pwcs`, and a `sorted(schema/*.cypher)` glob in two more
    modules — with nothing asserting they agreed.

    Measured: adding `schema/edtech_kg_tier3.cypher` carrying a real
    CREATE CONSTRAINT left the suite green at 1,396 passed while the loader
    never applied it. A whole tier silently undeclared — the exact failure #157
    exists to prevent, relocated from "one file read" to "one file list".

    There is one definition now, `etl.cypher_script.SCHEMA_FILES`, and every
    other module imports it. This is the assertion that holds that one list to
    the directory it claims to describe.
    """
    on_disk = tuple(sorted((ROOT / "schema").glob("*.cypher")))
    # MEMBERSHIP as sets, ORDER by the tier each file declares.
    #
    # Comparing tuples against `sorted()` was wrong in a way that only shows
    # up on the third tier: `sorted()` is lexicographic, so
    # `edtech_kg_tier10.cypher` lands BETWEEN tier 1 and tier 2, and any
    # non-`_tier` name sorts early. Someone adding a tier would have had to
    # declare it in lexicographic order, and the message told them to add it
    # to SCHEMA_FILES without saying where. Order is asserted below against
    # the banner each file actually carries, which is what the order means.
    assert set(cypher_script.SCHEMA_FILES) == set(on_disk), (
        f"schema/ holds {[f.name for f in on_disk]} and the loader declares "
        f"{[f.name for f in cypher_script.SCHEMA_FILES]}. A file here that "
        f"nothing declares is never applied; a file declared and missing "
        f"raises at load. Add it to etl.cypher_script.SCHEMA_FILES — and only "
        f"there, since every reader imports that tuple.")
    assert schema_source.SCHEMA_FILES is cypher_script.SCHEMA_FILES, (
        "tests/schema_source must re-export the loader's tuple, not restate "
        "it — two lists that agree today are the drift this test exists for")

    # **Order, by the banner each file declares.** `etl/cypher_script.py` says
    # the tuple is in tier order and that the order is pinned here; this is
    # what pins it. Read off the file rather than off the filename, so a third
    # tier can be called anything and still has to be declared in its place.
    declared = []
    for path in cypher_script.SCHEMA_FILES:
        text = path.read_text(encoding="utf-8")
        banners = re.findall(r"^// TIER (\d+)", text, re.M)
        assert banners, (
            f"{path.name} carries no `// TIER n` banner, so nothing says where "
            f"it belongs in the order. Add one, as both tiers have.")
        assert len(set(banners)) == 1, (
            f"{path.name} carries banners for tiers {sorted(set(banners))}; "
            f"one file, one tier — that is what 'tier is the file a "
            f"declaration lives in' means.")
        declared.append(int(banners[0]))
    assert declared == sorted(declared), (
        f"SCHEMA_FILES declares tiers in the order {declared}. It is applied "
        f"and read in this order, and both files are written to be read in "
        f"tier order. Note this is NOT lexicographic: a tier 10 file sorts "
        f"between 1 and 2 by name, which is why the banner decides.")


def test_both_tiers_are_actually_read():
    """Dropping tier 2 from the readers must fail loudly, not silently.

    Measured: removing `edtech_kg_tier2.cypher` from `cypher_script.SCHEMA_FILES`
    left every schema and loader test green — the load still succeeds with six
    fewer keys and two fewer indexes declared, and nothing said so. A comment in that module
    warned about exactly this and guarded nothing.

    Asserted on the applied text rather than on the tuple, because the failure
    that matters is a tier going unapplied, however that happens.
    """
    for name, text in (("tests", schema_text()),
                       ("the loader", cypher_script.schema_text())):
        assert "TIER 1 — uniqueness constraints" in text, (
            f"{name} is not reading tier 1")
        assert "TIER 2 — modelled, not yet populated" in text, (
            f"{name} is not reading tier 2 — it declares six keys and two "
            f"indexes, and a load without them succeeds silently")

    # **Driven through apply_schema with no `schema=`, which is the branch the
    # loader uses and the one nothing exercised.** `apply_schema` is called
    # without an explicit file in exactly one place — etl/load_pwcs.py — and the
    # only test that called it passed `schema=`, so `text = schema.read_text()
    # if schema else schema_text()` had no coverage on the production side at
    # all. Mutating that line to SCHEMA_FILES[0].read_text(), which silently
    # applies tier 1 and skips six constraints and an index, left the whole
    # suite green.
    #
    # Counting the readable text instead was near-tautological: it asserted that
    # a join of two files contains both files, which is true however the loader
    # behaves.
    class Recorder:
        def __init__(self):
            self.sent = []

        def run(self, statement):
            self.sent.append(statement)
            return {"records": []}

    recorder = Recorder()
    cypher_script.apply_schema(recorder, quiet=True)

    per_file = [len(split_statements("\n".join(
        strip_comment(line) for line in f.read_text(encoding="utf-8").splitlines())))
        for f in cypher_script.SCHEMA_FILES]
    # NOT `== 2`. That fought `test_the_declared_schema_is_every_schema_file`
    # in this same module: declaring a well-formed tier 3 — the thing that
    # test exists to force — failed here with `assert 3 == 2`. The sum below
    # carries the weight, and it does so for any number of files.
    assert len(per_file) == len(cypher_script.SCHEMA_FILES)
    assert len(recorder.sent) == sum(per_file), (
        f"apply_schema SENT {len(recorder.sent)} statements; the "
        f"{len(per_file)} schema files hold {sum(per_file)} "
        f"({' + '.join(map(str, per_file))})")

    # A SECOND count that does not go through the splitter. The comparison
    # above computes what it expects with the same `split_statements` and
    # `strip_comment` the loader uses, so a splitter that dropped or merged
    # statements would drop or merge them on both sides and stay invisible.
    # Counting the declaration keyword is independent of how the text is cut.
    # UNANCHORED on both sides, over comment-stripped text. The raw side was
    # anchored with `^\s*` and the sent side was not, so two valid statements
    # sharing a line — `…; CREATE INDEX ON :Completion(year);` — counted once
    # against twice and failed with "points AT the splitter" when the splitter
    # was right and this counter was wrong. Stripping comments keeps the one
    # independence that matters: this does not use `split_statements`.
    declared = sum(
        len(re.findall(r"CREATE (?:CONSTRAINT|INDEX)\b",
                       "\n".join(strip_comment(line) for line
                                 in f.read_text(encoding="utf-8").splitlines()),
                       re.I))
        for f in cypher_script.SCHEMA_FILES)
    sent_declarations = len(re.findall(
        r"CREATE (?:CONSTRAINT|INDEX)\b", "\n".join(recorder.sent), re.I))
    assert sent_declarations == declared, (
        f"the files declare {declared} constraints/indexes and apply_schema "
        f"sent {sent_declarations}. Counted without the splitter, so this "
        f"disagreeing with the statement count above points AT the splitter.")

    sent = "\n".join(recorder.sent)
    for label, tier in (("Course", "tier 1"), ("EarningsRecord", "tier 2")):
        assert label in sent, (
            f"apply_schema sent nothing mentioning {label} — {tier} is not "
            f"reaching the engine")


def test_the_dataset_card_counts_the_labels_that_hold_nothing():
    """DATASET-CARD said eight and named six of the twelve.

    That is what happens when a count is maintained by hand beside a schema
    that grew — the card was written when tier 2 held less. Derived from
    SCHEMA_FILES minus what the loaders write, so it cannot drift again
    without this failing.
    """
    from tests.schema_source import labels

    declared = {label for path in cypher_script.SCHEMA_FILES
                for label in labels(path.read_text(encoding="utf-8"))}
    loaders = sorted((ROOT / "etl").glob("load_*.py"))
    assert loaders, "no loaders found; the subtraction below would be vacuous"
    # **Two ways of naming a label, because there are two kinds of loader.**
    # The pattern finds literal labels — `CREATE (n:Course …` — and is blind
    # to a loader that parameterises them, which `etl/load_education.py`
    # does. It reported four written where the answer is seven, and the card
    # would have understated the graph with this check agreeing.
    #
    # So a loader may also DECLARE its labels in a `WRITES` tuple. Declared
    # beats inferred: the inference is a regex over source, and a loader that
    # says what it writes is not guessing.
    written = {label for loader in loaders
               for label in re.findall(r"\(\s*\w+:(\w+)",
                                       loader.read_text(encoding="utf-8"))
               if label in declared}
    for loader in loaders:
        declared_by = re.search(r"^WRITES = \(([^)]*)\)",
                                loader.read_text(encoding="utf-8"), re.M)
        if declared_by:
            written |= {name.strip().strip('"\'')
                        for name in declared_by.group(1).split(",")
                        if name.strip().strip('"\'') in declared}
    empty = declared - written

    card = (ROOT / "DATASET-CARD.md").read_text(encoding="utf-8")
    said = re.search(r"\*\*(\w+) labels are declared and (\w+) are written\*\*",
                     card)
    assert said, "the card no longer states the declared/written counts"
    words = {"four": 4, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "twelve": 12, "sixteen": 16}
    assert words.get(said.group(1).lower()) == len(declared), (
        f"the card says {said.group(1)} labels are declared; the schema "
        f"declares {len(declared)}")
    assert words.get(said.group(2).lower()) == len(written), (
        f"the card says {said.group(2)} are written; the loaders write "
        f"{len(written)}: {sorted(written)}")

    for label in sorted(empty):
        assert label in card, (
            f"{label} is declared and no loader writes it, and the card does "
            f"not name it among those holding nothing")


def test_a_commented_out_declaration_does_not_locate_a_label():
    """`constraint_line` split raw text, so a `//`-commented declaration
    matched — and `declaration_site` then resolved a label to a comment in the
    WRONG file, silently.

    Measured before the fix: blanking Place's documentation in tier 2 and
    adding `// CREATE CONSTRAINT ON (pl:Place) …` to tier 1 left the suite
    green, while two guards read their documentation window from a file that
    declares nothing.

    `labels()` already walked `code()` and
    `test_a_commented_out_constraint_is_not_counted` covered it there. This
    was the one path that skipped it.
    """
    live = "CREATE CONSTRAINT ON (a:Alpha) ASSERT a.id IS UNIQUE;"
    decoy = "// CREATE CONSTRAINT ON (b:Beta) ASSERT b.id IS UNIQUE;"

    assert constraint_line("Alpha", f"{decoy}\n{live}") == 1, (
        "the live declaration is on line 1 and the comment on line 0")
    assert constraint_line("Beta", f"{decoy}\n{live}") is None, (
        "a commented-out declaration located a label")


def test_a_label_declared_in_two_files_is_refused_not_picked():
    """`declaration_site` returned the FIRST hit, so a second declaration in
    another file was invisible and which one you got depended on tuple order —
    the shadowing this helper exists to remove."""
    real = declaration_site("Course")[0]
    other = next(f for f in SCHEMA_FILES if f != real)
    original = other.read_text(encoding="utf-8")
    try:
        other.write_text(
            original + "\nCREATE CONSTRAINT ON (c:Course) ASSERT c.url IS UNIQUE;\n",
            encoding="utf-8")
        with pytest.raises(AssertionError, match="declared in 2 schema files"):
            declaration_site("Course")
    finally:
        other.write_text(original, encoding="utf-8")
