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

# Defined HERE, in the module that does not import `probe_sced`, and re-exported
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


def resolve_titles(ny_titles: dict[str, list[str]],
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
    # The value is now a LIST of every code published under that title, not
    # one code. `new_york()["titles"]` used to collapse duplicates itself, so
    # 173 of New York's codes never arrived here at all — this function chose
    # between candidates a dict upstream had already narrowed to one.
    candidates: dict[str, set[str]] = {}
    for raw, codes in ny_titles.items():
        key = normalise(raw)
        if not key:
            # `normalise` can return "" — a title that is only a parenthetical
            # or only programme markers ("(Common Core)", "AP"). An empty key
            # matches every other title that normalises to empty, so it is
            # dropped rather than made a bucket everything falls into.
            continue
        candidates.setdefault(key, set()).update(
            [codes] if isinstance(codes, str) else codes)

    resolved, ambiguous = {}, []
    for key, codes in candidates.items():
        pure = sorted(c for c in codes if c not in extensions)
        preferred = pure or sorted(codes)
        resolved[key] = preferred[0]
        if len(preferred) > 1:
            ambiguous.append(key)
    return resolved, sorted(ambiguous)


def district_reach(ny_titles: dict[str, list[str]],
                   extensions: set[str] | None = None) -> dict:
    """How much of a real district's catalogue can reach a SCED code.

    The figure the whole probe exists for. A taxonomy nothing can join to is a
    document, not an identifier.
    """
    extensions = set(extensions or ())
    from etl import pwcs_source as source

    loaded = source.read()
    # `.get`, with a refusal naming the shape. `c["title"]` raised KeyError
    # from inside a comprehension if the loader ever stops publishing that
    # field — a traceback where every other failure in this module is a
    # MalformedSource with a message.
    if "courses" not in loaded:
        raise MalformedSource(
            f"the loaded catalogue has no `courses` key — it carries "
            f"{sorted(loaded)}. The district loader has changed shape.")
    blank = sum(1 for c in loaded["courses"]
                if not str(c.get("title") or "").strip())
    if blank:
        raise MalformedSource(
            f"{blank} of {len(loaded['courses'])} loaded courses have an "
            f"empty or missing `title`, so there is nothing to match a SCED "
            f"code against. A blank title normalises to the empty string and "
            f"would match every other blank one.")
    if any("title" not in c for c in loaded["courses"]):
        raise MalformedSource(
            f"{sum(1 for c in loaded['courses'] if 'title' not in c)} of "
            f"{len(loaded['courses'])} loaded courses carry no `title` field, "
            f"so there is nothing to match a SCED code against. The catalogue "
            f"loader has changed shape.")
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
    # Normalised ONCE per title. It was recomputed up to four times each —
    # in the dict key, the lookup, the membership test and the count — over
    # 791 titles, and it is a chain of four regex substitutions.
    keys = [normalise(t) for t in titles]
    matched = {k: by_name[k] for k in keys if k in by_name}
    reachable = sum(1 for k in keys if k in by_name)

    # The same count with the parenthetical rule OFF, so the page's claim that
    # the figure is "generous, deliberately" carries a number the probe
    # printed. It quoted "58 rather than 67" as typed text on a page whose
    # first line says nothing on it is typed.
    strict_key = {normalise(t, drop_parentheticals=False)
                  for t in ny_titles}
    strict_key.discard("")
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
    # Separators stripped, so `courseCode`, `course-code` and `course code`
    # all reduce to the same thing as `course_code`. Lower-casing alone
    # matched `scedCode` (via "sced") and missed `courseCode`, because
    # `"coursecode"` is not `"course_code"` — and the field it missed is one
    # of the two that would carry a district's SCED code. The zero this
    # produces is what the schema recommendation rests on, so a marker that
    # silently fails to match is a false zero.
    # ENDS with the marker, not merely contains it. `"coursecode" in flat`
    # also matches `coursecodedescription` and `state_code_note` — fields that
    # describe a code rather than carry one — and a description landing in
    # `code_fields` makes `publishes_sced_code` count a course as publishing a
    # code it does not have. `sced` stays a containment test because
    # `scedCourseCode` and `SCED Code` are both real shapes and both carry one.
    flattened = {f: re.sub(r"[^a-z0-9]", "", f.lower()) for f in fields}
    code_fields = [f for f, flat in flattened.items()
                   if "sced" in flat
                   or flat.endswith(("coursecode", "statecode"))]
    # Per COURSE, not per (course × field) pair. The sum ran over both loops,
    # so a record carrying two code fields counted twice while being reported
    # as a count of courses — the units problem one line down from the one this
    # figure was introduced to fix.
    # Guarded like `title` is. `loaded["courses"]` raised KeyError while the
    # field inside it got a message — the outer shape is the one more likely
    # to change, and it was the one unguarded.
    published = sum(1 for c in loaded["courses"]
                    if any(SCED_CODE.match(str(c.get(f, "")).strip())
                           for f in code_fields))

    return {"district_courses": len(titles),
            "fields_published": fields,
            # `publishes_sced_code: 0` has TWO meanings and the schema
            # recommendation rests on one of them: no field exists that could
            # carry a code, versus a field exists and every value in it fails
            # to be one. The first says the district has no concept of a SCED
            # code; the second says it has one and leaves it blank, which is a
            # different argument. `sced_code_fields` tells them apart — empty
            # means the first — and this states it rather than leaving a
            # reader to infer it from two keys.
            "no_field_to_carry_one": not code_fields,
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
