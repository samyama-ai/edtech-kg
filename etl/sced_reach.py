"""What a real district's catalogue can actually join to.

Split out of `etl/probe_sced.py` when it passed the 500-line review limit, and
split by SUBJECT: everything here is the MEASUREMENT — a district's course
titles against New York's published codes. `probe_sced.py` keeps reading the
sources and printing the page.

The split follows where the defects were. Both blockers on this half were about
which code a title resolves to rather than about reading a file: a normalised
title collapses `Geometry` and `Geometry (Common Core)` onto one key, and the
answer used to be whichever row the sheet listed last.
"""

from __future__ import annotations

import re

# Defined HERE, in the module that has no imports of its own, and re-exported
# by `probe_sced`. Both halves raise the one exception and both read the one
# code shape, and putting them in the half that imports this one would be a
# cycle.
SCED_CODE = re.compile(r"\A\d{5}\Z")


class MalformedSource(Exception):
    """A source that answered, but not with what it publishes."""


def normalise(title: str, drop_parentheticals: bool = True) -> str:
    """A course title reduced to what two states might plausibly share.

    The programme markers go: PWCS publishes `AP Biology` and New York
    publishes `AP Biology` too, but it also publishes `Biology` where PWCS has
    `AICE Biology (AS Level)`. Stripping them measures the best case for
    matching — which is the honest thing to measure, because a worse
    normalisation would understate what SCED could reach.
    """
    text = re.sub(r"\*+", "", title or "").lower()
    # The parenthetical qualifier goes first, while it is still bracketed:
    # `AICE Biology (AS Level)` is the same course as `Biology` for this
    # purpose, and leaving `as level` on the end meant the comparison was
    # stricter than the page claimed it was.
    if drop_parentheticals:
        text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(ap|ib|aice|advanced placement|honors|dual enrollment)\b", " ", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return " ".join(text.split())


def resolve_titles(ny_titles: dict[str, str],
                   extensions: set[str]) -> tuple[dict[str, str], list[str]]:
    """Normalised title to the ONE code it should resolve to, and the ties.

    Two defects lived in the one-line dict comprehension this replaces.

    **It was last-wins over a lossy key.** `normalise` strips parentheticals,
    so `Geometry (02072)` and `Geometry (Common Core) (02072CC)` collapse to
    the same key and whichever row came later in the sheet won. 32 of New
    York's normalised titles have more than one raw title behind them, so
    which code the published example list reports was row-order dependent and
    silently arbitrary.

    **And an extension code could win.** New York's eleven `CC`/`L` codes are
    the state adding to the taxonomy, not using it — the page says so, and says
    counting them as SCED alignment would overstate it. `Geometry` resolved to
    `02072CC` for exactly that reason, and `Geometry` is in the page's own
    published list of matching courses.

    So a pure five-digit SCED code beats an extension, and among equals the
    lowest code wins, which is stable across runs. Where a tie survives both
    rules it is REPORTED rather than resolved: the page can say which titles
    are ambiguous instead of quietly picking one.
    """
    candidates: dict[str, set[str]] = {}
    for raw, code in ny_titles.items():
        candidates.setdefault(normalise(raw), set()).add(code)

    resolved, ambiguous = {}, []
    for key, codes in candidates.items():
        pure = sorted(c for c in codes if c not in extensions)
        preferred = pure or sorted(codes)
        resolved[key] = preferred[0]
        if len(preferred) > 1:
            ambiguous.append(key)
    return resolved, sorted(ambiguous)


def district_reach(ny_titles: dict[str, str],
                   extensions: set[str] | None = None) -> dict:
    """How much of a real district's catalogue can reach a SCED code.

    The figure the whole probe exists for. A taxonomy nothing can join to is a
    document, not an identifier.
    """
    extensions = set(extensions or ())
    from etl import pwcs_source as source

    loaded = source.read()
    titles = [c["title"] for c in loaded["courses"]]
    if not titles:
        raise MalformedSource(
            "the loaded catalogue holds no courses — refusing to report a "
            "reach of zero when nothing was compared")
    by_name, ambiguous = resolve_titles(ny_titles, extensions)

    # Keyed on the NORMALISED title, so the numerator and the denominator
    # count the same thing. Keying on the raw title made `reachable_by_name`
    # a count of distinct titles while `district_courses` counted rows, and
    # two courses sharing a name would have made the percentage disagree with
    # itself.
    matched = {normalise(t): by_name[normalise(t)]
               for t in titles if normalise(t) in by_name}
    reachable = sum(1 for t in titles if normalise(t) in by_name)

    # The same count with the parenthetical rule OFF, so the page's claim that
    # the figure is "generous, deliberately" carries a number the probe
    # printed. It quoted "58 rather than 67" as typed text on a page whose
    # first line says nothing on it is typed.
    strict_key = {normalise(t, drop_parentheticals=False): code
                  for t, code in ny_titles.items()}
    strict = sum(1 for t in titles
                 if normalise(t, drop_parentheticals=False) in strict_key)

    # Does the district publish a SCED code of its own? If it did, none of the
    # name matching above would be needed — and that is the whole finding.
    #
    # This asks whether the record carries a FIELD for one, not whether any of
    # its text happens to be five digits. The earlier version scanned every
    # string value, so a course titled `12345` or a URL segment would have
    # counted — it returned 0 for the right answer by the wrong route, and the
    # zero is what the schema recommendation rests on.
    fields = sorted({key for c in loaded["courses"] for key in c})
    code_fields = [f for f in fields
                   if any(marker in f.lower()
                          for marker in ("sced", "course_code", "state_code"))]
    # Per COURSE, not per (course × field) pair. The sum ran over both loops,
    # so a record carrying two code fields counted twice while being reported
    # as a count of courses — the units problem one line down from the one this
    # figure was introduced to fix.
    published = sum(1 for c in loaded["courses"]
                    if any(SCED_CODE.match(str(c.get(f, "")).strip())
                           for f in code_fields))

    return {"district_courses": len(titles),
            "fields_published": fields,
            "sced_code_fields": code_fields,
            "publishes_sced_code": published,
            "reachable_by_name": reachable,
            # The same measurement with the leniency turned off, so the page's
            # "it is generous, deliberately" is a printed comparison rather
            # than a sentence.
            "reachable_without_the_parenthetical_rule": strict,
            "distinct_titles_matched": len(matched),
            # Matches whose code is a state EXTENSION rather than a SCED code.
            # New York adding to the taxonomy is not the district reaching it,
            # and the page says so — so if this is ever non-zero the headline
            # is counting something it argues against.
            "matched_via_state_extension": sorted(
                k for k, v in matched.items() if v in extensions),
            # Normalised titles New York publishes under more than one code
            # even after preferring the SCED one. Reported, not resolved.
            "ambiguous_titles": ambiguous,
            "examples": dict(sorted(matched.items())[:8])}
