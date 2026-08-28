"""New York's Comprehensive Course Catalog — the one SCED-keyed state file.

Split from `etl/probe_sced.py` when that file passed the 500-line review
limit, on the boundary its own docstring already draws: NCES publishes the
taxonomy, New York publishes a state directory keyed to it, and reading them
are two jobs.

This half answers "does any state actually use SCED?", which is the half
edtech-kg#48 turns on. `sced_reach` then asks what a district can join to.
"""

from __future__ import annotations

import io
import re
import zipfile

from etl.probe_cipsoc import rows, sheets
from etl.sced_reach import SCED_CODE, MalformedSource

NEW_YORK = ("https://www.p12.nysed.gov/irs/courseCatalog/"
            "sced-course-codes-2024-25.xlsx")

# What the first two New York columns must be called for the positional reads
# below to mean what they say. Taken from the published file rather than
# guessed: the course NAME is under "Course Code Description", and "Course
# Description" — the long text — is a different column, two along.
#
# (The five-digit-code rule these used to sit beside is `SCED_CODE`, which
# moved to `etl/sced_reach.py` with the matching.)
NY_CODE_HEADER = "course code (course id)"

NY_TITLE_HEADER = "course code description"


def _titles(courses) -> dict:
    """Course title to EVERY code published under it.

    A dict keyed by title loses duplicates silently, and this file's whole
    finding is about which of several codes a title resolves to. It was
    `{title: code}`, so New York's 2,012 rows collapsed to 1,839 entries and
    173 codes were gone before `resolve_titles` — which exists to decide
    between exactly those — could see them. A rule cannot be applied to a
    value the dict feeding it already discarded.

    Sorted, so the value does not depend on the order of the sheet. That
    dependence was the defect one layer down.
    """
    out: dict[str, set] = {}
    for row in courses:
        if len(row) > 1 and row[1].strip():
            out.setdefault(row[1].strip(), set()).add(row[0].strip())
    return {title: sorted(codes) for title, codes in out.items()}


def new_york(payload: bytes) -> dict:
    """The one state directory this repo has found that is SCED-keyed."""
    # The BYTES, not the URL. Fetching lives with the caller, so this module
    # imports nothing from the one that imports it — and a test can hand it a
    # workbook without faking a transport.
    with zipfile.ZipFile(io.BytesIO(payload)) as book:
        return _new_york(book)


def squashed(text: str) -> str:
    """Case, spaces and punctuation removed — the one header-matching policy.

    `probe_sced._master` uses the same rule. A heading that gains an internal
    space or a hyphen is a cosmetic change, and these readers name columns
    precisely so a cosmetic change does not decide anything.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _new_york(book: zipfile.ZipFile) -> dict:
    parts = sheets(book)
    name = next((n for n in parts if "all courses" in n.lower()), None)
    if name is None:
        raise MalformedSource(
            f"no course sheet in the New York catalogue — it has {sorted(parts)}")

    body = rows(book, parts[name])
    if len(body) < 2:
        raise MalformedSource(
            f"the New York sheet {name!r} has no data rows — refusing to report "
            f"a catalogue of nothing")
    # The header row EXCLUDED wherever it repeats, not just at the top. Any
    # non-empty column 0 counted as a course, so a sheet that repeats its
    # header — which is how NCES pages a long table — inflates the count the
    # page quotes.
    header = body[0]
    courses = [r for r in body[1:]
               if r and r[0].strip() and r[0].strip() != header[0].strip()]
    if not courses:
        raise MalformedSource(f"the New York sheet {name!r} parsed to zero courses")
    # The header row itself must have content. A blank first row passes the
    # length guard above and then `header[0]` raises IndexError from inside the
    # check that exists to catch a restructured export — a traceback instead of
    # the message.
    if not header or not header[0].strip():
        raise MalformedSource(
            f"the New York sheet {name!r} opens with a blank row, so its "
            f"columns cannot be checked — the export has been restructured")

    # Column 0 is the code and column 1 the title. Checked rather than assumed:
    # a reordered export would otherwise be read silently, and every figure
    # below would be a plausible count of the wrong column.
    # Matched the SAME WAY `_master` matches its own — squashed, so case and
    # spacing do not decide it. Exact equality here and loose matching there
    # meant an extra internal space stopped the New York run and passed on
    # master, and the master file already ships a cell with a leading space.
    if not (squashed(header[0]) == squashed(NY_CODE_HEADER)
            and len(header) > 1 and header[1].strip().lower() == NY_TITLE_HEADER):
        raise MalformedSource(
            f"the New York columns are {header[:3]}, not a code column followed "
            f"by a title column — the export has been restructured and the "
            f"figures need re-checking rather than re-reading")

    codes = [r[0].strip() for r in courses]
    pure = [c for c in codes if SCED_CODE.match(c)]

    # ONE unit throughout: distinct codes. `courses` and `sced_codes` counted
    # ROWS while `state_extensions` counted distinct codes, so the printed
    # table only reconciled against `courses` by the accident of this file
    # carrying no repeated extension code. Rows are still reported, separately
    # and named as rows, because a catalogue that repeats a code is worth
    # seeing rather than silently collapsing.
    distinct, distinct_pure = set(codes), set(pure)
    return {"source": NEW_YORK, "columns": header,
            "rows": len(codes),
            "courses": len(distinct),
            "sced_codes": len(distinct_pure),
            "state_extensions": sorted(distinct - distinct_pure),
            "subject_prefixes": len({c[:2] for c in distinct_pure}),
            # The question #34 asks, answered against a real published file
            # rather than against the standard.
            "publishes_sequence": any("sequence" in h.lower() for h in header),
            # EVERY code per title, not the last one to appear.
            #
            # `{title: code}` collapsed 2,012 rows to 1,839, so 173 codes were
            # gone before `resolve_titles` — which exists to decide between
            # exactly those — could see them.
            "titles": _titles(courses)}
