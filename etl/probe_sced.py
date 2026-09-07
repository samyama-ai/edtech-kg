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
from pathlib import Path
from datetime import datetime, timezone

# `probe_cipsoc`'s reader, not a second one. `sheets` resolves through the
# relationship table rather than filename order, and `rows` places cells by
# their `r` attribute — Excel omits a blank cell, so appending in order shifts
# every later column left. A second reader is how this file missed
# ` Course Title`.
from etl.identity import USER_AGENT
from etl.provenance import write_record
from etl.probe_cipsoc import rows, sheets
# The reach measurement lives next door; this module reads the sources and
# prints the page. `MalformedSource` is raised by both, so it stays here.
from etl.new_york_catalog import NEW_YORK, new_york
from etl.sced_reach import MalformedSource, district_reach

LANDING = "https://nces.ed.gov/forum/sced.asp"

# The workbook URL is READ from the landing page, not pinned — a pinned one
# reports SCED 13.0 for ever once NCES ships v14, which is the stale constant
# this page's corrections section exists to avoid.
#
# Below is the URL it was pinned to, for the record. NOT a fallback: one that
# kicks in when the landing page changes shape is the stale constant again,
# wearing a guard.
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
    highest = max(int(v) for _, v in found)
    at_highest = {href for href, v in found if int(v) == highest}
    if len(at_highest) > 1:
        # A tie broken by the order of the page is not a choice. Two hrefs for
        # one version means NCES publishes it twice — mirrored, or moved — and
        # which copy this reads decides what every figure describes.
        raise MalformedSource(
            f"{LANDING} lists {len(at_highest)} links for SCED v{highest}: "
            f"{sorted(at_highest)}. This reads one and cannot choose between "
            f"them.")
    href, version = at_highest.pop(), highest
    # PINNED to https on the NCES host. `urljoin` takes whatever scheme the
    # fetched HTML offers, so a page carrying
    # `file:///etc/passwd/SCEDv99File_x.xlsx` would be downloaded and read. A
    # thin threat model — this reads one government page — and one line.
    resolved = urllib.parse.urljoin(LANDING, href)
    parts = urllib.parse.urlparse(resolved)
    if parts.scheme != "https" or parts.netloc != urllib.parse.urlparse(LANDING).netloc:
        raise MalformedSource(
            f"{LANDING} points the master workbook at {resolved} — not https "
            f"on the same host. This reads one government page and will not "
            f"follow it somewhere else.")
    return resolved, int(version)


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
    # ALL matches, then exactly one — `next(...)` took the first, so a
    # workbook carrying SCED 13.0 and 14.0 picked by archive order and every
    # figure would describe a version the page does not name.
    #
    # Matched by SHAPE, since the sibling filter below takes any sheet with
    # "Element" in it: `SCED Elements` would satisfy both and trip this
    # refusal over a name that is not a second version.
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
    # The header row EXCLUDED wherever it repeats, not just at the top. Any
    # non-empty column 0 counted as a course, so a sheet that repeats its
    # header — which is how NCES pages a long table — inflates the count the
    # page quotes.
    header = body[0]
    courses = [r for r in body[1:]
               if r and r[0].strip() and r[0].strip() != header[0].strip()]
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

    # And the column NAMES, as `new_york()` pins its own. `courses` is counted
    # by `r[0].strip()` — column 0 assumed to be the title — so a reordered
    # sheet would keep parsing and count something else, which is the
    # positional read every other reader in this repo was moved off. Matched
    # loosely, because a re-cased or re-spaced heading is a cosmetic change.
    def squashed(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    if squashed(header[0]) != "coursetitle":
        raise MalformedSource(
            f"the SCED sheet {catalogue!r} opens with {header[0]!r}, not the "
            f"course title. Its rows are counted by column 0, so a reordered "
            f"sheet would count something else and keep going. Header: "
            f"{header}")

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
        if bucket is elements and "consecutive sequence of courses" in definition:
            # From the ELEMENT bucket only. Any bucket matched, so an
            # attribute carrying the phrase would be quoted as "SCED's element
            # list includes Sequence of Course" — which is the page's answer
            # to edtech-kg#48 and would be about the wrong thing.
            #
            # Collected, not overwritten: two kept whichever row came last.
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


def probe(quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    taxonomy = master()
    state = new_york(fetch(NEW_YORK))
    # `titles` STAYS in the payload. `pop` removed it from the dict the caller
    # is handed, and a copy without it did the same more quietly — so `--json`
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
        # The COLUMNS and the CODES, not just their counts. The page names
        # both — "eight columns", "01003CC, 03001L and nine more" — and
        # printing only a count leaves the names typed on a page that says
        # nothing is. Mutating either in the page left the suite green.
        print(f"  columns it publishes             "
              f"{len(state['columns'])}: {', '.join(state['columns'])}")
        print(f"  the extension codes              "
              f"{', '.join(state['state_extensions'])}")
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
        print("\n  matched — courses that already had a national identity\n")
        for title in reach["matched_titles"]:
            print(f"    {title}")
        print("\n  unmatched — what a district is distinctive for\n")
        for title in reach["unmatched_titles"]:
            print(f"    {title}")
        print()
        print(f"  titles NY publishes twice        "
              f"{len(reach['ambiguous_titles']):>8}"
              "   <- resolved to the SCED code")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_sced\n")

    return {"retrieved_at": stamp, "sced": taxonomy,
            "new_york": state, "district": reach}


#: A trimmed record of one measured run, committed so the page can be checked
#: without reaching the network. `docs/sources/sced.md` quotes figures and
#: names from a district catalogue that `pwcs_source.read()` fetches — 960
#: pages from one school district — and `conftest.py` refuses that traffic
#: from CI in as many words. Asserting the page against this instead makes
#: the check hermetic; a second test re-runs against live sources where the
#: cache exists and diffs against it, so upstream drift surfaces once as "the
#: record is stale" rather than as prose edits on an unrelated commit.
RECORD = Path(__file__).resolve().parents[1] / "docs" / "sources" / "sced-measured.json"


def record(state: dict, reach: dict) -> dict:
    """The subset of a run the page is checked against.

    Trimmed deliberately: every field here is quoted on the page, and a record
    carrying more would drift in ways nothing reads.
    """
    return {
        "_": ("A trimmed record of one measured run, committed so the page can "
              "be checked without reaching the network. Refresh with "
              "`python -m etl.probe_sced --record`."),
        "new_york": {k: state[k] for k in
                     ("columns", "rows", "courses", "sced_codes",
                      "state_extensions", "publishes_sequence")},
        "district": {
            **{k: reach[k] for k in
               ("district_courses", "reachable_by_name",
                "reachable_without_the_parenthetical_rule",
                "matched_via_state_extension",
                "matched_titles", "unmatched_titles")},
            "ambiguous_titles": len(reach["ambiguous_titles"]),
            # The CTE programmes the page names as what SCED misses. That is
            # the argument rather than an illustration, so it is recorded as
            # measured data — the sample above may not happen to include them.
            "named_cte_unmatched": sorted(
                t for t in reach["all_unmatched"]
                if any(m in t.lower() for m in
                       ("turfgrass", "landscaping", "horticulture",
                        "greenhouse"))),
        },
    }


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    parser.add_argument("--record", action="store_true",
                        help=f"Refresh {RECORD.name} from a live run.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json or args.record)
    except MalformedSource as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.record:
        write_record(RECORD, record(result["new_york"], result["district"]))
        # Relative to the REPO, not the cwd, and guarded. `relative_to` RAISES
        # when its argument is not an ancestor, so this crashed from any cwd
        # outside the repo — `~`, a sibling checkout — and it crashed AFTER
        # the write landed, so the record was correct and the command still
        # exited on a traceback. Same two lines as `probe_licences`.
        root = Path(__file__).resolve().parents[1]
        where = RECORD.relative_to(root) if RECORD.is_relative_to(root) else RECORD
        print(f"wrote {where}")
        return 0
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
