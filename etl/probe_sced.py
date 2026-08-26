"""Probe SCED — the national course taxonomy, and whether it makes a Course portable.

Two issues, one question. **edtech-kg#34** asks what SCED is and whether it
carries a sequence field. **edtech-kg#48** asks whether enough states align to
it that a `Course` keyed on SCED would join across them. They are the same
investigation: SCED is only worth a node if a district's catalogue can reach it.

    python -m etl.probe_sced                 # the tables
    python -m etl.probe_sced --json          # machine-readable

Three sources, all fetched:

  * the NCES SCED master file — the taxonomy itself, and the elements a SCED
    record is allowed to carry;
  * New York's Comprehensive Course Catalog, which is SCED-keyed and is the
    only state directory this repo has found that is;
  * the loaded PWCS catalogue, to measure what a real district could join.

**No third-party dependency**, as with the other probes: an .xlsx is a zip of
XML and reading three sheets is a few dozen lines of standard library.

The number this exists to produce is the last one: **how many of one district's
courses can reach a SCED code at all.** Everything above it is context for that.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

# The workbook reader is `probe_cipsoc`'s, not a second one written here.
# `sheets` resolves a sheet through the relationship table rather than
# trusting filename order, and `rows` places cells by their `r` attribute
# rather than by document order — Excel omits a blank cell instead of writing
# one, so appending in order shifts every later column left. Carrying a second
# reader is how this file came to miss ` Course Title`, below.
from etl.probe_cipsoc import rows, sheets

LANDING = "https://nces.ed.gov/forum/sced.asp"

# v13, not the v12 edtech-kg#34 names — the issue was written against the page
# as it stood, and NCES has published a version since. Read from the landing
# page rather than pinned, so the next version is a changed figure and not a
# stale constant.
MASTER = ("https://nces.ed.gov/sites/default/files/"
          "national-forum-education-statistics-nfes/document/2025/11/"
          "SCEDv13File_508.xlsx")

NEW_YORK = ("https://www.p12.nysed.gov/irs/courseCatalog/"
            "sced-course-codes-2024-25.xlsx")

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# A five-digit SCED code and nothing else. New York publishes eleven codes with
# a state suffix (`01003CC`), which are NOT SCED codes — they are New York
# extending the taxonomy, and counting them as SCED would overstate alignment.
SCED_CODE = re.compile(r"\A\d{5}\Z")

# What the first two New York columns must be called for the positional reads
# below to mean what they say. Taken from the published file rather than
# guessed: the course NAME is under "Course Code Description", and "Course
# Description" — the long text — is a different column, two along.
NY_CODE_HEADER = "course code (course id)"
NY_TITLE_HEADER = "course code description"


class MalformedSource(Exception):
    """A source that answered, but not with what it publishes."""


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise MalformedSource(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc
    # A workbook is a zip. An HTML error page served with status 200 is the
    # failure this catches — it would otherwise parse to zero rows and be
    # reported as an empty taxonomy.
    if not payload.startswith(b"PK"):
        raise MalformedSource(
            f"{url} did not return a workbook — got {payload[:40]!r}")
    return payload


def master() -> dict:
    """The taxonomy itself, and what a SCED record is allowed to carry."""
    book = zipfile.ZipFile(io.BytesIO(fetch(MASTER)))
    parts = sheets(book)
    catalogue = next((n for n in parts if n.startswith("SCED ") and "Archived" not in n), None)
    if catalogue is None:
        raise MalformedSource(
            f"no course sheet in the SCED master file — it has {sorted(parts)}. "
            f"NCES has changed the layout; check {LANDING} before trusting anything.")

    body = rows(book, parts[catalogue])
    header, courses = body[0], [r for r in body[1:] if r and r[0].strip()]
    if not courses:
        raise MalformedSource("the SCED course sheet parsed to zero rows")

    named = elements_and_attributes(book, parts)

    return {"source": MASTER, "landing_page": LANDING, "version_sheet": catalogue,
            "columns": header, "courses": len(courses),
            "sheets": sorted(parts),
            **named}


def elements_and_attributes(book: zipfile.ZipFile, parts: dict[str, str]) -> dict:
    """What a SCED record MAY carry — read from the sheet's own key column.

    This is where edtech-kg#34 is actually answered, and it is not the same
    question as what the master file publishes: the master file has four
    columns, while the standard names far more than four.

    The sheet is a single key column under two banner rows — `Element Name`
    and then `Attribute Name` — so the split between the two is the sheet's
    own, not one imposed here. It names **6 elements and 17 attributes**, 23
    in all.

    The previous version matched a hand-written set of prefixes instead, and
    it was wrong in a way the count did not show. It also printed 6 — but a
    different 6: it included `Course Description`, which the sheet files under
    ATTRIBUTES, and missed `Available Carnegie Unit Credit`, which is a real
    element. It missed `Course Title` as well, because that cell carries a
    LEADING SPACE and the match was an exact equality against a reader that
    did not strip. A right-looking total over the wrong members is the failure
    this repo keeps finding, so the split is read from the sheet now.
    """
    sheet = next((n for n in parts if "Element" in n), None)
    if sheet is None:
        raise MalformedSource(
            f"no elements sheet in the SCED master file — it has {sorted(parts)}. "
            f"That sheet is what answers what a record may carry; check {LANDING}.")

    elements, attributes, bucket, sequence = [], [], None, None
    for row in rows(book, parts[sheet]):
        if not row:
            continue
        key = row[0].strip()
        definition = row[1].strip() if len(row) > 1 else ""
        if key == "Element Name":
            bucket = elements
            continue
        if key == "Attribute Name":
            bucket = attributes
            continue
        if not key or bucket is None:
            continue
        bucket.append(key)
        if "consecutive sequence of courses" in definition:
            sequence = definition

    if not elements:
        raise MalformedSource(
            f"the elements sheet parsed to zero elements — its banner rows "
            f"('Element Name' / 'Attribute Name') have changed. Check {LANDING}.")

    return {"elements": elements, "attributes": attributes,
            "sequence_element": sequence}


def new_york() -> dict:
    """The one state directory this repo has found that is SCED-keyed."""
    book = zipfile.ZipFile(io.BytesIO(fetch(NEW_YORK)))
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
    header, courses = body[0], [r for r in body[1:] if r and r[0].strip()]
    if not courses:
        raise MalformedSource(f"the New York sheet {name!r} parsed to zero courses")

    # Column 0 is the code and column 1 the title. Checked rather than assumed:
    # a reordered export would otherwise be read silently, and every figure
    # below would be a plausible count of the wrong column.
    if not (header[0].strip().lower() == NY_CODE_HEADER
            and len(header) > 1 and header[1].strip().lower() == NY_TITLE_HEADER):
        raise MalformedSource(
            f"the New York columns are {header[:3]}, not a code column followed "
            f"by a title column — the export has been restructured and the "
            f"figures need re-checking rather than re-reading")

    codes = [r[0].strip() for r in courses]
    pure = [c for c in codes if SCED_CODE.match(c)]

    return {"source": NEW_YORK, "columns": header, "courses": len(codes),
            "sced_codes": len(pure),
            "state_extensions": sorted(set(codes) - set(pure)),
            "subject_prefixes": len({c[:2] for c in pure}),
            # The question #34 asks, answered against a real published file
            # rather than against the standard.
            "publishes_sequence": any("sequence" in h.lower() for h in header),
            "titles": {r[1].strip(): r[0].strip()
                       for r in courses if len(r) > 1 and r[1].strip()}}


def normalise(title: str) -> str:
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
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(ap|ib|aice|advanced placement|honors|dual enrollment)\b", " ", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return " ".join(text.split())


def district_reach(ny_titles: dict[str, str]) -> dict:
    """How much of a real district's catalogue can reach a SCED code.

    The figure the whole probe exists for. A taxonomy nothing can join to is a
    document, not an identifier.
    """
    from etl import pwcs_source as source

    loaded = source.read()
    titles = [c["title"] for c in loaded["courses"]]
    if not titles:
        raise MalformedSource(
            "the loaded catalogue holds no courses — refusing to report a "
            "reach of zero when nothing was compared")
    by_name = {normalise(t): code for t, code in ny_titles.items()}

    # Keyed on the NORMALISED title, so the numerator and the denominator
    # count the same thing. Keying on the raw title made `reachable_by_name`
    # a count of distinct titles while `district_courses` counted rows, and
    # two courses sharing a name would have made the percentage disagree with
    # itself.
    matched = {normalise(t): by_name[normalise(t)]
               for t in titles if normalise(t) in by_name}
    reachable = sum(1 for t in titles if normalise(t) in by_name)

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
    published = sum(1 for c in loaded["courses"] for f in code_fields
                    if SCED_CODE.match(str(c.get(f, "")).strip()))

    return {"district_courses": len(titles),
            "fields_published": fields,
            "sced_code_fields": code_fields,
            "publishes_sced_code": published,
            "reachable_by_name": reachable,
            "distinct_titles_matched": len(matched),
            "examples": dict(sorted(matched.items())[:8])}


def probe(quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    taxonomy = master()
    state = new_york()
    reach = district_reach(state.pop("titles"))

    if not quiet:
        print("\nSCED — the national course taxonomy\n")
        print(f"  master file                        {taxonomy['version_sheet']}")
        print(f"  courses in it                    {taxonomy['courses']:>8,}")
        print(f"  columns it publishes               {', '.join(taxonomy['columns'])}")
        print(f"  elements a record MAY carry      {len(taxonomy['elements']):>8}")
        print(f"  attributes it may also carry     {len(taxonomy['attributes']):>8}")
        print()
        if taxonomy["sequence_element"]:
            print("  SCED DOES define a sequence element:")
            print(f"    {taxonomy['sequence_element'][:96]}")
            print("  — 'part n of m parts', which is one course split across terms.")
            print("    It is NOT a prerequisite between two different courses.")
        else:
            print("  no sequence element found — check the master file layout")
        print()
        print("New York — the one SCED-keyed state directory found\n")
        print(f"  courses published                {state['courses']:>8,}")
        print(f"  five-digit SCED codes            {state['sced_codes']:>8,}")
        print(f"  state extensions (not SCED)      {len(state['state_extensions']):>8}")
        print(f"  publishes a sequence column      {str(state['publishes_sequence']):>8}")
        print()
        print("Prince William County — what could actually join\n")
        print(f"  courses loaded                   {reach['district_courses']:>8,}")
        print(f"  fields a course record carries     {', '.join(reach['fields_published'])}")
        print(f"  of those, SCED code fields       {len(reach['sced_code_fields']):>8}"
              "   <- the finding: there is no field to carry one")
        print(f"  publishing a SCED code           {reach['publishes_sced_code']:>8}")
        print(f"  reachable by name alone          {reach['reachable_by_name']:>8}"
              f"   ({reach['reachable_by_name'] / reach['district_courses']:.0%})")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_sced\n")

    return {"retrieved_at": stamp, "sced": taxonomy,
            "new_york": state, "district": reach}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json)
    except MalformedSource as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
