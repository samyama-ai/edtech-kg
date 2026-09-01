"""What the schema actually commits a node to carrying.

`schema/edtech_kg.cypher` declares **keys**. It declares almost nothing else —
measured, not asserted: no non-key property appears in it at all. The other
properties a graph has are the ones a loader writes, and only four labels have
a loader.

That gap is the point rather than a nuisance. A traversal naming
`o.name` on an `Occupation` parses, looks like an answer, and reaches for
something nothing in this repo has promised to write. `tests/
test_question_traversals.py` uses this to make that visible instead of leaving
it for a reader to notice.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "edtech_kg.cypher"


def declared() -> dict[str, set[str]]:
    """Label to the properties this repo has committed to.

    Two sources, and both are needed. The constraint declares the KEY. The
    loaders declare everything else, because a property nothing writes is a
    property that will not be there.
    """
    found: dict[str, set[str]] = {}
    schema = SCHEMA.read_text(encoding="utf-8")
    for var, label, prop in re.findall(
            r"CREATE CONSTRAINT ON \((\w+):(\w+)\) ASSERT \1\.(\w+)", schema):
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
