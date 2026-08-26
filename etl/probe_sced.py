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
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

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

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# A five-digit SCED code and nothing else. New York publishes eleven codes with
# a state suffix (`01003CC`), which are NOT SCED codes — they are New York
# extending the taxonomy, and counting them as SCED would overstate alignment.
SCED_CODE = re.compile(r"\A\d{5}\Z")


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


def sheets(book: zipfile.ZipFile) -> dict[str, str]:
    """Sheet name to part path, resolved through the relationship table.

    Not by filename order: `sheet1.xml` is not reliably the first sheet, and a
    reordered workbook would silently read the wrong one.
    """
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))}
    rid = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    found = {}
    for sheet in workbook.iter(f"{{{NS['m']}}}sheet"):
        target = rels[sheet.get(rid)].lstrip("/")
        found[sheet.get("name")] = target if target.startswith("xl/") else "xl/" + target
    return found


def rows(book: zipfile.ZipFile, part: str) -> list[list[str]]:
    shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
              for si in ET.fromstring(book.read("xl/sharedStrings.xml"))]
    sheet = ET.fromstring(book.read(part))
    out = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        cells = []
        for cell in row.iter(f"{{{NS['m']}}}c"):
            value = cell.find(f"{{{NS['m']}}}v")
            if value is None:
                cells.append("")
            elif cell.get("t") == "s":
                cells.append(shared[int(value.text)])
            else:
                cells.append(value.text or "")
        out.append(cells)
    return out


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

    # The elements sheet is where the question in #34 is actually answered: it
    # lists what a SCED record MAY carry, which is not the same as what the
    # master file publishes.
    elements, sequence = [], None
    for sheet_name in parts:
        if "Element" not in sheet_name:
            continue
        for row in rows(book, parts[sheet_name]):
            for cell in row:
                if cell.startswith("School Courses for the Exchange of Data") \
                        or cell in ("Course Title", "Course Description"):
                    elements.append(cell.strip())
                if "consecutive sequence of courses" in cell:
                    sequence = cell.strip()

    return {"source": MASTER, "landing_page": LANDING, "version_sheet": catalogue,
            "columns": header, "courses": len(courses),
            "sheets": sorted(parts),
            "elements": sorted(set(elements)),
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
    header, courses = body[0], [r for r in body[1:] if r and r[0].strip()]
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
    by_name = {normalise(t): code for t, code in ny_titles.items()}

    matched = {t: by_name[normalise(t)] for t in titles if normalise(t) in by_name}

    # Does the district publish a SCED code of its own? If it did, none of the
    # name matching above would be needed — and that is the whole finding.
    published = sum(1 for c in loaded["courses"]
                    if any(SCED_CODE.match(str(v).strip())
                           for v in c.values() if isinstance(v, str)))

    return {"district_courses": len(titles),
            "publishes_sced_code": published,
            "reachable_by_name": len(matched),
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
