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

Nothing here reaches an engine.
"""

from __future__ import annotations

import re

from etl.cypher_script import split_statements, strip_comment
from etl import cypher_script
from tests import schema_source
from tests.schema_source import ROOT, schema_text


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
    # IN ORDER, not as sets. `etl/cypher_script.py` says the tuple is written
    # tier 1 first and that the order matters to the banner guards — swapping
    # it fails `test_a_label_sits_under_the_tier_banner_it_belongs_to`. A set
    # comparison left that sentence unexecutable, which is how a comment
    # becomes decoration. `sorted()` puts `edtech_kg.cypher` before
    # `edtech_kg_tier2.cypher`, which is tier order; a tier whose filename
    # broke that would fail here and should.
    assert tuple(cypher_script.SCHEMA_FILES) == on_disk, (
        f"schema/ holds {[f.name for f in on_disk]} and the loader declares "
        f"{[f.name for f in cypher_script.SCHEMA_FILES]}. A file here that "
        f"nothing declares is never applied; a file declared and missing "
        f"raises at load. Add it to etl.cypher_script.SCHEMA_FILES — and only "
        f"there, since every reader imports that tuple.")
    assert schema_source.SCHEMA_FILES is cypher_script.SCHEMA_FILES, (
        "tests/schema_source must re-export the loader's tuple, not restate "
        "it — two lists that agree today are the drift this test exists for")


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
    declared = sum(
        len(re.findall(r"^\s*CREATE (?:CONSTRAINT|INDEX)\b",
                       f.read_text(encoding="utf-8"), re.M | re.I))
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
