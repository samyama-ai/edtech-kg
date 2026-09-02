"""What the schema actually commits a node to carrying.

`schema/edtech_kg.cypher` declares **keys** in its constraints and
**attributes** in its PROPERTIES block, each naming the field a source
publishes it as (#123). Before that block the schema declared keys and nothing
else, so a label with no loader could commit to nothing and `Occupation.name`
was undeclared while every source publishes it.

DECLARED MEANS A LOADER WRITES IT, and the distinction is load-bearing. The
schema also carries a PUBLISHED_NOT_LOADED block — `Course.description` and
`Course.grade_levels`, which the catalogue publishes and `etl/load_pwcs.py`
does not extract (#137). `declared()` does not read it. If it did, Q9 and Q14
would lose their `NEEDS:` annotations and look served while returning null,
which is the failure this whole apparatus exists to make visible.

A traversal naming `o.name` on an `Occupation` parses, looks like an answer,
and reaches for something nothing has promised to write.
`tests/test_question_traversals.py` uses this to say so.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "edtech_kg.cypher"


def declared() -> dict[str, set[str]]:
    """Label to the properties this repo has committed to.

    THREE sources, and the order matters. The constraint declares the key. The
    schema's PROPERTIES block declares the attributes, each naming the source
    field it comes from (#123). The loaders declare what they additionally
    write, because a property nothing writes is a property that will not be
    there.

    The PROPERTIES block is what changed. Before it, the schema declared keys
    and nothing else, so this function inferred attributes from loader source
    — which meant a label with no loader could commit to nothing, and
    `Occupation.name` was undeclared while every source publishes it.
    """
    found: dict[str, set[str]] = {}
    schema = SCHEMA.read_text(encoding="utf-8")
    for var, label, prop in re.findall(
            r"CREATE CONSTRAINT ON \((\w+):(\w+)\) ASSERT \1\.(\w+)", schema):
        found.setdefault(label, set()).add(prop)

    for label, prop in re.findall(r"^//\s+(\w+)\.(\w+)\s+<-", declared_block(), re.M):
        found.setdefault(label, set()).add(prop)

    for source in sorted((ROOT / "etl").glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for match in re.finditer(
                r'upsert\(\s*engine,\s*"(\w+)",\s*"(\w+)",[^,]+,\s*\{(.*?)\}',
                text, re.S):
            label, key, body = match.groups()
            found.setdefault(label, set()).add(key)
            found[label] |= set(re.findall(r'"(\w+)":', body))
    return found


def block(name: str = "PROPERTIES") -> str:
    """One of the schema's marked blocks, between its own markers.

    Sliced rather than pattern-matched across the whole file: a bare
    `Label.property <-` regex would also read the NOT-declared paragraph below
    it, and the PUBLISHED_NOT_LOADED block beside it, both of which exist
    precisely to say what the schema does NOT commit to.

    `PROPERTIES` ends before `PUBLISHED_NOT_LOADED` begins, and the search for
    the end marker starts at the opening one, so the two do not read each
    other however they are ordered in the file.
    """
    schema = SCHEMA.read_text(encoding="utf-8")
    start = schema.index(f"// {name}\n")
    end = schema.index(f"// END {name}", start)
    return schema[start:end]


def declared_block() -> str:
    """Kept as a name because tests and the schema comment both use it."""
    return block("PROPERTIES")


def accesses(cypher: str) -> dict[str, set[str]]:
    """Label to the properties a statement reaches for.

    Aliases are resolved from the statement's own patterns, so `c.name` is
    read as `Course.name` only where `c` was bound to a `Course`. An alias
    bound nowhere is skipped rather than guessed at.
    """
    used: dict[str, set[str]] = {}
    for statement in cypher.split(";"):
        alias = dict(re.findall(r"\((\w+):(\w+)", statement))
        for var, prop in re.findall(r"\b(\w+)\.(\w+)", statement):
            if var in alias:
                used.setdefault(alias[var], set()).add(prop)

        # INLINE pattern properties too. `MATCH (c:Completion {award_level:
        # "X"})` reaches for `award_level` exactly as much as `c.award_level`
        # does, and reading only the dotted form missed it — so a query could
        # match on an undeclared property and this would report no gap.
        # Anonymous nodes are included: `(:School {ncessch: …})` names a
        # label, which is all that is needed to attribute the property.
        for label, body in re.findall(r"\(\s*\w*\s*:(\w+)\s*\{([^}]*)\}", statement):
            # Anchored to the start or a comma. A bare `(\w+)\s*:` also matches
            # inside the VALUE — `{url: "https://…"}` yielded a property named
            # `https` — so the extractor invented a gap the schema could never
            # declare, in a check whose whole job is to say what is missing.
            used.setdefault(label, set()).update(
                re.findall(r"(?:^|,)\s*(\w+)\s*:", body))
    return used


def undeclared(cypher: str) -> set[str]:
    """`Label.property` for everything reached for and never promised."""
    known = declared()
    return {f"{label}.{prop}"
            for label, props in accesses(cypher).items()
            for prop in props
            if prop not in known.get(label, set())}
