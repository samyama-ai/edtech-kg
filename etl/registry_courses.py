"""What one Registry course node says about its prerequisites.

Split out of `etl/probe_registry.py` for #58, which sweeps all 47,862 published
courses rather than the 600 the sampling probe reads. The sweep exists to
REPLACE the sample's figure, so it has to ask the identical question — and the
question was not askable from outside: `text()` and `as_list()` lived inside
`course_prerequisites`, reachable only by re-implementing them.

That re-implementation is the failure this module prevents, and it is not
hypothetical. `probe_registry.is_reference` carries the record of it: the typed
`ceterms:prerequisite` branch and the `ceterms:requires` branch had drifted to
two different tests of the same thing, the strict one on the path that never
fires and the loose one on the path that does. Two callers reading the same
records through two copies of this logic would disagree, and the disagreement
would surface as a changed headline figure with no changed finding behind it.

Split by SUBJECT, as `registry_read.py` was: that module is *how the Registry
is read* — transport, failures, sampling. This one is *what a course record
says*. `probe_registry.py` keeps the counting and the tables.

The vocabulary, which the split must not blur:

    STATES      the course says something about a prerequisite
    RESOLVES    it says it as a pointer at a thing, not as prose
    EMPTY       it has a prerequisite block carrying nothing — no description,
                an empty one, or the word "None"

`STATES` and `EMPTY` are exclusive by construction; a course that only says
"Prerequisites: None" states nothing. Counting either as the other is what
moves the rate `docs/sources/ctdl.md` quotes.
"""

from __future__ import annotations

#: Terms whose presence would mean a prerequisite is stated in a resolvable
#: way. A resolvable prerequisite points at something a learner completes. A
#: competency target is a different claim — it says what you must be able to
#: do, not which course you must have taken — so it is deliberately not here.
#: `docs/sources/ctdl.md` argues about the Course -> Course edge and this list
#: must match it.
RESOLVABLE = ("ceterms:targetLearningOpportunity", "ceterms:targetCredential")

#: A description that is a statement that there are NO prerequisites. Not free
#: text naming a course, so it must not count towards the stated rate.
SAYS_NONE = ("none", "n/a", "na", "-")


def text(value) -> str:
    """A CTDL language map, which is a dict, a bare string, or a list of either.

    A list-valued map used to read as empty, which silently turned a stated
    prerequisite into a course with none.
    """
    if isinstance(value, list):
        return " ".join(text(item) for item in value)
    if isinstance(value, dict):
        inner = value.get("en-US") or value.get("en") or next(
            iter(value.values()), "")
        return text(inner)
    # Anything else — a number, a bool — becomes a string rather than being
    # handed to .lower() as-is.
    return value if isinstance(value, str) else ("" if value is None else
                                                 str(value))


def as_list(value) -> list:
    """`ceterms:requires` is a list when a course has several conditions and a
    bare object when it has one. Assuming the list raised AttributeError on the
    single-condition form."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def is_reference(value) -> bool:
    """Does this point at something, or is it prose?

    One test, called from both branches. They had drifted apart: the typed
    `ceterms:prerequisite` branch required an @id or a URI-shaped string while
    the `ceterms:requires` branch accepted any truthy value — and since every
    resolvable hit in the sample arrives through `requires`, the strict test was
    on the path that never fires and the loose one on the path that does.

    A publisher writing `ceterms:targetLearningOpportunity: "PSYC101"` — free
    text in the target field, which is the behaviour `docs/sources/ctdl.md`
    documents — would otherwise count as a resolved edge, moving the one figure
    that page exists to produce on the strength of a string.
    """
    if isinstance(value, dict):
        return bool(value.get("@id"))
    return isinstance(value, str) and value.strip().lower().startswith(
        ("http", "ce-"))


def is_course(node) -> bool:
    """A `@graph` carries many node types; only Course nodes are counted.

    Matched on the substring because CTDL publishes `ceterms:Course` while
    schema.org-flavoured records publish `Course`, and both are courses.
    """
    return isinstance(node, dict) and "Course" in str(node.get("@type", ""))


def classify(node: dict) -> dict:
    """What ONE course says about prerequisites.

    Per COURSE, not per condition. Without that, a course carrying both
    "Prerequisites" and "Prerequisite (recommended)" incremented the count
    twice, so the figure counted profiles while the documents read it as a
    share of courses.

    Returns `states` / `resolves` / `empty` as booleans, plus any prose found,
    so a caller can count courses and collect examples without walking the
    conditions a second time and reaching a different answer.
    """
    states = resolves = empty = False
    prose: list[str] = []

    typed = node.get("ceterms:prerequisite")
    if typed:
        # Present but empty is not a reference. Counting the key alone would
        # credit the Registry with resolvable edges it does not publish — the
        # opposite of the finding this measures.
        states = True
        resolves = any(is_reference(v) for v in as_list(typed))

    for condition in as_list(node.get("ceterms:requires")):
        if not isinstance(condition, dict):
            continue
        if "prereq" not in text(condition.get("ceterms:name")).lower():
            continue
        # The same test the typed branch applies, not a weaker one.
        if any(is_reference(v) for key in RESOLVABLE
               for v in as_list(condition.get(key))):
            states = resolves = True
            continue
        described = text(condition.get("ceterms:description")).strip()
        if described and described.lower() not in SAYS_NONE:
            states = True
            prose.append(described)
        else:
            empty = True

    return {"states": states, "resolves": resolves,
            # A course that states something is not also "stated but empty",
            # even if one of its several conditions was blank.
            "empty": empty and not states,
            "prose": prose,
            # Recorded separately so a sweep can name the publishers that use
            # the typed edge — the whole point of #58 if the count is not zero.
            "uses_typed_edge": bool(typed)}


def courses_in(envelope) -> list[dict]:
    """The Course nodes one Registry envelope carries.

    One `@graph` can hold several, which is why counting envelopes and counting
    courses are different numbers.
    """
    if not isinstance(envelope, dict):
        return []           # the list shape is checked; its elements are not
    resource = envelope.get("decoded_resource") or {}
    return [node for node in (resource.get("@graph") or [resource])
            if is_course(node)]


def publisher_of(envelope: dict) -> str:
    return str(envelope.get("published_by") or envelope.get("owned_by")
               or "unknown")
