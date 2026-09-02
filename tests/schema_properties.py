"""What a query can actually reach, and what the schema merely names.

Two different questions, and conflating them is what this module got wrong.

`schema/edtech_kg.cypher` declares **keys** in its constraints and names
**attributes** in its PROPERTIES block, each with the field a source publishes
it as (#123). That block is a statement about SOURCES. It is not a claim that
anything writes them, and it must not be read as one:

    $ grep -rln "MERGE (\|CREATE (" etl/*.py     -> engine, cypher_script, load_pwcs
    load_pwcs writes                             -> Course, Pathway, Requirement, Subject

Nothing loads `Occupation`, `Programme`, `Institution`, `School`, `District` or
`Completion`. `SOC2018Title`, `INSTNM`, `school_name` and `lea_name` appear in
no loader at all; `CTOTALT` and `AWLEVEL` appear in a probe.

So `declared()` — which is what tells a query it may reach for a property
without a `NEEDS:` line — is keys plus **what a loader writes**, and nothing
else. An earlier version of this docstring asserted that the PROPERTIES block
meant "a loader writes it". It does not, for eight of its ten entries, and
saying so dropped 33 `NEEDS:` annotations from queries that still return null:
`Q2` reaches for `o.name` on a graph holding zero `Occupation` nodes.

`named_in_schema()` is the other question, kept separate and used by the tests
that hold the block to its sources.
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

    # The PROPERTIES block is NOT read here. It names attributes and their
    # source fields; it does not write them, and eight of its ten labels have
    # no loader whatsoever. Adding it made every query naming one of those look
    # served while returning null. See the module docstring.
    for source in sorted((ROOT / "etl").glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for match in re.finditer(
                r'upsert\(\s*engine,\s*"(\w+)",\s*"(\w+)",[^,]+,\s*\{(.*?)\}',
                text, re.S):
            label, key, body = match.groups()
            found.setdefault(label, set()).add(key)
            found[label] |= set(re.findall(r'"(\w+)":', body))
    return found


def named_in_schema() -> dict[str, set[str]]:
    """Label to the attributes the schema NAMES, with a source field behind each.

    The other question from `declared()`, and the reason they are two
    functions: this is what the schema commits to describing, that is what a
    query can reach. Today the second is a subset of the first by a wide
    margin, and pretending otherwise is what #123's first attempt did.
    """
    found: dict[str, set[str]] = {}
    for label, prop in re.findall(r"^//\s+(\w+)\.(\w+)\s+<-", block(), re.M):
        found.setdefault(label, set()).add(prop)
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
    opening, closing = f"// {name}\n", f"// END {name}"
    # A MESSAGE, not `ValueError: substring not found` from `str.index`, which
    # names neither the marker nor the file and sends the reader nowhere.
    if opening not in schema:
        raise ValueError(
            f"{SCHEMA} has no `{opening.strip()}` marker — it was renamed or "
            f"removed, and every attribute test reads this block through it.")
    start = schema.index(opening)
    if closing not in schema[start:]:
        raise ValueError(
            f"{SCHEMA} opens `{opening.strip()}` and never closes it with "
            f"`{closing}`, so the block would run to the end of the file.")
    return schema[start:schema.index(closing, start)]


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
