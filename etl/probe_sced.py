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
import urllib.parse
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
# The reach measurement lives next door; this module reads the sources and
# prints the page. `MalformedSource` is raised by both, so it stays here.
from etl.sced_reach import MalformedSource, SCED_CODE, district_reach

LANDING = "https://nces.ed.gov/forum/sced.asp"

# v13, not the v12 edtech-kg#34 names — the issue was written against the page
# as it stood, and NCES has published a version since.
#
# READ from the landing page, which is what this comment claimed and the code
# did not do. `MASTER` was a hard-pinned v13 URL and `LANDING` was fetched
# nowhere, so "the next version is a changed figure and not a stale constant"
# described a mechanism that did not exist: when NCES ships v14 the probe would
# have reported SCED 13.0 indefinitely, which is precisely the stale constant
# the page's own corrections section claims to avoid.
#
# Kept below as the URL this was pinned to, for the record and for nothing
# else. It is not a fallback: a fallback that kicks in silently when the
# landing page changes shape is the stale constant again, wearing a guard.
PINNED_WAS = ("https://nces.ed.gov/sites/default/files/"
              "national-forum-education-statistics-nfes/document/2025/11/"
              "SCEDv13File_508.xlsx")

# `SCEDv{N}File` in the href, because the landing page also links the previous
# version — v12 and v13 are both there today. The HIGHEST is the current one,
# and taking the first link found would have pinned whichever NCES happens to
# list first.
MASTER_LINK = re.compile(r"""href=["']([^"']*SCEDv(\d+)File[^"']*\.xlsx)["']""",
                         re.IGNORECASE)

#: The course sheet, named for the version it carries — `SCED 13.0`. Matched
#: by SHAPE so it cannot collide with the elements sheet, which is selected by
#: a substring: a sheet called `SCED Elements` would satisfy both.
SCED_SHEET = re.compile(r"\ASCED\s+\d+(?:\.\d+)*\Z")

NEW_YORK = ("https://www.p12.nysed.gov/irs/courseCatalog/"
            "sced-course-codes-2024-25.xlsx")

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# A five-digit SCED code and nothing else. New York publishes eleven codes with
# a state suffix (`01003CC`), which are NOT SCED codes — they are New York
# extending the taxonomy, and counting them as SCED would overstate alignment.
# What the first two New York columns must be called for the positional reads
# below to mean what they say. Taken from the published file rather than
# guessed: the course NAME is under "Course Code Description", and "Course
# Description" — the long text — is a different column, two along.
NY_CODE_HEADER = "course code (course id)"
NY_TITLE_HEADER = "course code description"


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


def master_file() -> tuple[str, int]:
    """The current SCED master workbook, read from the landing page.

    Returns the absolute URL and the version number in its filename, so the
    version this page reports is the version it downloaded rather than a name
    inside a sheet — those can disagree, and the sheet name is the one a
    restructure changes without the file changing.

    Refuses rather than falling back. If NCES restyles the landing page this
    stops, loudly, on the run that would otherwise have reported last year's
    taxonomy as this year's.
    """
    page = fetch_text(LANDING)
    found = MASTER_LINK.findall(page)
    if not found:
        raise MalformedSource(
            f"no SCEDv<N>File .xlsx link on {LANDING} — the master workbook is "
            f"read from that page rather than pinned, so a restructured "
            f"landing page has to stop the run. It was pinned to "
            f"{PINNED_WAS} when this was written; check whether that still "
            f"resolves before re-pinning anything.")
    href, version = max(found, key=lambda pair: int(pair[1]))
    return urllib.parse.urljoin(LANDING, href), int(version)


def fetch_text(url: str) -> str:
    """One HTML page, or a refusal naming it.

    Separate from `fetch`, which insists on a workbook's PK magic — the whole
    point of that guard is that an HTML error page is not a workbook, so it
    cannot be reused for a page that is meant to be HTML.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise MalformedSource(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc


def master() -> dict:
    """The taxonomy itself, and what a SCED record is allowed to carry."""
    url, version = master_file()
    # In a `with`. An unclosed `ZipFile` holds its buffer until the garbage
    # collector gets to it, and `probe()` opens two of them per run.
    with zipfile.ZipFile(io.BytesIO(fetch(url))) as book:
        return _master(book, url, version)


def _master(book: zipfile.ZipFile, url: str, version: int) -> dict:
    parts = sheets(book)
    # ALL matches, then exactly one. `next(...)` took the first of however
    # many matched, so a workbook carrying `SCED 13.0` and `SCED 14.0` — which
    # is how NCES would ship a transition — silently picked whichever came
    # first in the archive, and every figure below would describe a version
    # the page does not name.
    # `SCED <version>`, matched by SHAPE. `startswith("SCED ")` also matches
    # anything else beginning with the word — and the sibling filter below
    # takes any sheet with "Element" in it, so a sheet called "SCED Elements"
    # would satisfy both: the course-sheet check would see two candidates and
    # refuse the whole run over a name that is not a second version at all.
    # Today's names do not collide ("SCED 13.0" and "Elements and
    # Attributes"), so this is a false refusal waiting on a rename.
    named = [n for n in parts if SCED_SHEET.match(n)]
    if len(named) > 1:
        raise MalformedSource(
            f"the workbook holds {len(named)} current SCED sheets {sorted(named)}; "
            f"this reads one and cannot choose between them. NCES has shipped a "
            f"transition, and which version the figures describe has to be a "
            f"decision rather than an archive ordering.")
    catalogue = named[0] if named else None
    if catalogue is None:
        raise MalformedSource(
            f"no course sheet in the SCED master file — it has {sorted(parts)}. "
            f"NCES has changed the layout; check {LANDING} before trusting anything.")

    body = rows(book, parts[catalogue])
    if len(body) < 2:
        raise MalformedSource(
            f"the SCED sheet {catalogue!r} has no data rows — refusing to "
            f"report a taxonomy of nothing")
    header, courses = body[0], [r for r in body[1:] if r and r[0].strip()]
    if not courses:
        raise MalformedSource("the SCED course sheet parsed to zero rows")
    # The same guard `new_york()` got, on the same shape in the same file. It
    # reached one function and not the other: `header[0]` is read below, and
    # a sheet whose first row is empty in column 0 raised IndexError from
    # inside the check meant to report a layout change.
    if not header or not header[0].strip():
        raise MalformedSource(
            f"the SCED sheet {catalogue!r} opens with a blank first column, so "
            f"its layout cannot be checked — NCES has restructured the file")

    # `split`, not `named` — that name already held the list of candidate
    # course sheets forty lines up, and rebinding it to an unrelated dict in
    # the same function is how a reader loses track of which one a later line
    # means.
    split = elements_and_attributes(book, parts)

    return {"source": url, "landing_page": LANDING,
            # The version in the FILENAME the landing page pointed at, beside
            # the sheet name. They agree today and a restructure separates
            # them, which is worth seeing rather than resolving silently.
            "version": version, "version_sheet": catalogue,
            "columns": header, "courses": len(courses),
            "sheets": sorted(parts),
            **split}


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
    # Same rule as the course sheet: all matches, then exactly one. `"Element"
    # in n` is a loose substring — `Elements`, `Element Definitions` and
    # `Data Elements` all match — and `next(...)` took whichever the archive
    # listed first, so the 6/17 split could be read off a different sheet than
    # the one the page names with nothing saying so.
    candidates = [n for n in parts if "Element" in n]
    if len(candidates) > 1:
        raise MalformedSource(
            f"{len(candidates)} sheets match 'Element' {sorted(candidates)}; "
            f"the element/attribute split is read from one of them and this "
            f"cannot choose. NCES has restructured the workbook.")
    sheet = candidates[0] if candidates else None
    if sheet is None:
        raise MalformedSource(
            f"no elements sheet in the SCED master file — it has {sorted(parts)}. "
            f"That sheet is what answers what a record may carry; check {LANDING}.")

    elements, attributes, bucket, sequence = [], [], None, []
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
            # COLLECTED, not overwritten. This was `sequence = definition`, so
            # a workbook defining the phrase twice kept whichever came last
            # and said nothing — and the page quotes this definition as the
            # answer to edtech-kg#48. Which of two definitions it quoted would
            # have been an artefact of row order.
            sequence.append(definition)

    if not elements:
        raise MalformedSource(
            f"the elements sheet parsed to zero elements — its banner rows "
            f"('Element Name' / 'Attribute Name') have changed. Check {LANDING}.")

    return {"elements": elements, "attributes": attributes,
            "sequence_element": sequence[0] if sequence else None,
            # Reported so a second definition is visible rather than resolved
            # by row order. One today.
            "sequence_definitions": len(sequence)}


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


def new_york() -> dict:
    """The one state directory this repo has found that is SCED-keyed."""
    with zipfile.ZipFile(io.BytesIO(fetch(NEW_YORK))) as book:
        return _new_york(book)


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
    header, courses = body[0], [r for r in body[1:] if r and r[0].strip()]
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
    if not (header[0].strip().lower() == NY_CODE_HEADER
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
            # This was `{title: code}`, so New York's 2,012 rows collapsed to
            # 1,839 entries and 173 codes were gone before anything downstream
            # could see them — including `resolve_titles`, which exists to
            # decide between exactly those. The rule it applies (a five-digit
            # SCED code beats a state extension) cannot run on a value that was
            # already thrown away by the dict that fed it.
            "titles": _titles(courses)}


def probe(quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    taxonomy = master()
    state = new_york()
    # `titles` STAYS in the payload. `pop` removed it from the dict the caller
    # is handed, and building a copy without it did the same thing more
    # quietly — the mutation went and the omission stayed, so `--json` still
    # reported a New York block missing the one field the reach measurement
    # is computed from. A machine-readable payload that drops its own input
    # cannot be re-checked, which is the only reason to emit one.
    reach = district_reach(state["titles"], set(state["state_extensions"]))

    if not quiet:
        print("\nSCED — the national course taxonomy\n")
        print(f"  master file                        {taxonomy['version_sheet']}")
        # The version from the FILENAME the landing page pointed at. Reading
        # it is the whole reason that page is fetched, and it was in the JSON
        # and nowhere a human looks — so the change that stopped the version
        # being a stale constant was invisible in the output people read.
        print(f"  version on the landing page        v{taxonomy['version']}")
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
        print(f"  rows in the sheet                {state['rows']:>8,}")
        print(f"  distinct course codes            {state['courses']:>8,}")
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
        # Guarded. `district_reach` refuses an empty catalogue, so this cannot
        # divide by zero today — but the two are in different modules and the
        # print is where a reader looks, so it does not rely on that.
        share = (f"{reach['reachable_by_name'] / reach['district_courses']:.0%}"
                 if reach["district_courses"] else "no courses")
        print(f"  reachable by name alone          {reach['reachable_by_name']:>8}"
              f"   ({share})")
        print(f"  ... without the parenthetical rule "
              f"{reach['reachable_without_the_parenthetical_rule']:>6}"
              "   <- the strict comparison")
        print(f"  ... via a NY state extension     "
              f"{len(reach['matched_via_state_extension']):>8}"
              "   <- not SCED alignment")
        print(f"  titles NY publishes twice        "
              f"{len(reach['ambiguous_titles']):>8}"
              "   <- resolved to the SCED code")
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
