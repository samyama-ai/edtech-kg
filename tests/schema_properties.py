r"""What a query can actually reach, and what the schema merely names.

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

import ast
import inspect
import pathlib
import re

from etl.engine import upsert

ROOT = pathlib.Path(__file__).resolve().parents[1]

# One definition of "the schema", in the module whose subject that is. This file
# had its own copy of SCHEMA_FILES and schema_text() -- the same two lines twice,
# which is the drift the split was supposed to prevent, reintroduced by the
# split itself.
from tests.schema_source import SCHEMA_FILES, schema_text  # noqa: E402


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
    schema = schema_text()
    for var, label, prop in re.findall(
            r"CREATE CONSTRAINT ON \((\w+):(\w+)\) ASSERT \1\.(\w+)", schema):
        found.setdefault(label, set()).add(prop)

    # The PROPERTIES block is NOT read here. It names attributes and their
    # source fields; it does not write them, and eight of its ten labels have
    # no loader whatsoever. Adding it made every query naming one of those look
    # served while returning null. See the module docstring.
    for source in sorted((ROOT / "etl").glob("*.py")):
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for label, key, props in upserts(tree):
            found.setdefault(label, set()).add(key)
            found[label] |= props
    return found


#: `upsert`'s parameter names, READ OFF THE FUNCTION rather than restated. A
#: rename there is exactly the ordinary refactor this parser is supposed to
#: survive, and hardcoding the names is how it stopped surviving one.
_PARAMS = inspect.getfullargspec(upsert).args
LABEL_ARG, KEY_ARG, PROPS_ARG = _PARAMS[1], _PARAMS[2], _PARAMS[4]


def upserts(tree: ast.AST) -> list[tuple[str, str, set[str]]]:
    """Every `upsert(engine, "Label", "key", …, {…})` and the properties it writes.

    AST, not a regex over source text. The regex required a DICT LITERAL as the
    fifth argument — `upsert(…, {"name": …})` — and a loader that builds its
    properties first, which is ordinary when some of them are conditional,
    matched nothing. `Course.name` then read as undeclared and every query
    naming it was reported as reaching past the schema. A parser that breaks on
    a refactor while its subject is unchanged is the brittle-source-coupling
    this repo keeps finding, in the module that decides what "declared" means.

    A dict passed by NAME is followed: keys from the literal it was assigned,
    plus any `properties["x"] = …` written afterwards. That is the shape a
    conditional property takes, and the point of reading it is that an
    optional property is still a written one.
    """
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # KEYWORDS TOO. Requiring five positional arguments meant
        # `upsert(engine, "X", "k", v, properties=props)` registered nothing —
        # not even the label and key — and the point of moving off the regex
        # was to stop breaking on an ordinary rewrite. A keyword argument is
        # one.
        supplied = list(node.args) + [None] * 5
        by_name = {kw.arg: kw.value for kw in node.keywords}
        if len(node.args) < 5 and not by_name:
            continue
        called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if called != "upsert":
            continue
        # The names come from `etl.engine.upsert`'s own signature, not from a
        # guess. This looked for `properties=` and the parameter is `props=` —
        # so the keyword branch was dead for the only spelling a caller could
        # write, and worse than dead: `props=` left `properties` as None, the
        # call was skipped entirely, and the LABEL AND KEY went with it.
        # `Course.name` then reads as undeclared and every query naming it is
        # reported as reaching past the schema — the failure this rewrite
        # exists to remove, one identifier over.
        label = supplied[1] if supplied[1] is not None else by_name.get(LABEL_ARG)
        key = supplied[2] if supplied[2] is not None else by_name.get(KEY_ARG)
        properties = (supplied[4] if supplied[4] is not None
                      else by_name.get(PROPS_ARG))
        if properties is None or not all(
                isinstance(a, ast.Constant) and isinstance(a.value, str)
                for a in (label, key) if a is not None):
            continue
        if label is None or key is None:
            continue
        found.append((label.value, key.value,
                      property_names(scope_of(tree, node), properties)))
    return found


def scope_of(tree: ast.AST, call: ast.Call) -> ast.AST:
    """The innermost function containing `call`, or the module.

    A dict passed by name is resolved WITHIN this, not across the file. Walking
    the module meant every assignment to a matching name anywhere contributed
    keys: two loaders in one module each building their own `properties` would
    merge into both labels, and `declared()` would report properties as written
    that no upsert for that label writes. A query would then lose its `NEEDS:`
    line and answer null on a loaded district — the failure this module exists
    to prevent, arriving through the parser meant to prevent it.
    """
    innermost = tree
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(child is call for child in ast.walk(node)):
            # The innermost wins: a nested function is inside its parent's
            # walk too, and the nearer scope is the one that binds.
            if innermost is tree or any(child is node
                                        for child in ast.walk(innermost)):
                innermost = node
    return innermost


def property_names(tree: ast.AST, argument: ast.AST) -> set[str]:
    """The string keys of a dict argument, literal or built under a name."""
    if isinstance(argument, ast.Dict):
        return {k.value for k in argument.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    if not isinstance(argument, ast.Name):
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        # `properties = properties` recurses without bound. Contrived, and one
        # line to refuse.
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Name)
                and node.value.id == argument.id):
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                # `properties = {...}`
                if isinstance(target, ast.Name) and target.id == argument.id:
                    names |= property_names(tree, node.value)
                # `properties["description"] = ...`
                if (isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == argument.id
                        and isinstance(target.slice, ast.Constant)
                        and isinstance(target.slice.value, str)):
                    names.add(target.slice.value)
    return names


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
    schema = schema_text()
    opening, closing = f"// {name}\n", f"// END {name}"
    # A MESSAGE, not `ValueError: substring not found` from `str.index`, which
    # names neither the marker nor the file and sends the reader nowhere.
    if opening not in schema:
        raise ValueError(
            f"neither schema file has a `{opening.strip()}` marker — it was "
            f"renamed or removed ({', '.join(f.name for f in SCHEMA_FILES)})"
            f" — "
            f"removed, and every attribute test reads this block through it.")
    start = schema.index(opening)
    if closing not in schema[start:]:
        raise ValueError(
            f"the schema opens `{opening.strip()}` and never closes it with "
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
