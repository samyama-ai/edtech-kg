"""Probe the statewide course directories — counts, and whether prerequisites exist.

The question #40 asked: does any state publish a course list carrying
prerequisites? Two of the five checked are machine-readable and neither does.
This script is how that was established, so the answer can be re-derived rather
than believed.

    python -m etl.probe_state_courses          # the table
    python -m etl.probe_state_courses --json   # machine-readable

Texas and New York serve their files to a plainly-identified request. Florida,
Virginia and California did not on 2026-08-18 — recorded as `blocked` rather
than as an absence, because a blocked fetch is not the same as data that does
not exist. #50 exists to find out which.

**No third-party dependency**, as with the other probes: the Texas file is CSV
and the New York one is a zip of XML.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

TEXAS = ("https://tealprod.tea.state.tx.us/TWEDS/66/0/0/0/"
         "CodeTable/DownloadSingle/7999%7CC022")
NEW_YORK = "https://www.p12.nysed.gov/irs/courseCatalog/sced-course-codes-2024-25.xlsx"

# Attempted and blocked on 2026-08-18. Kept in the output so the table's
# silence is explained rather than read as "these states publish nothing".
BLOCKED = [
    ("Florida", "https://www.fldoe.org/policy/articulation/ccd/", "403"),
    ("Virginia", "https://www.doe.virginia.gov/data-policy-funding/data-reports/"
                 "data-collection/master-schedule-collection/msc-code-values", "403"),
    ("California", "https://www.cde.ca.gov/ds/sp/cl/systemdocs.asp", "redirect"),
]

# Any of these appearing in a course record would mean a prerequisite is stated.
PREREQ_TERMS = ("prerequisit", "pre-requisit", "must have completed",
                "before taking", "prior to", "successful completion")


def fetch(url: str, expect: bytes | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"unreachable: {url} ({exc})") from exc
    if expect and not payload.startswith(expect):
        raise ValueError(
            f"{url} did not return the expected format — got {len(payload)} bytes "
            f"starting {payload[:16]!r}. The file may have moved."
        )
    return payload


def texas() -> dict:
    rows = list(csv.reader(io.StringIO(fetch(TEXAS).decode("utf-8-sig", "replace"))))
    if len(rows) < 2:
        raise ValueError("Texas C022 returned no rows — refusing to report that as a count")
    header = rows[0]
    blob = " ".join(" ".join(r) for r in rows).lower()
    return {
        "state": "Texas",
        "source": TEXAS,
        "format": "CSV",
        "courses": len(rows) - 1,
        "fields": header,
        "prerequisite_terms": {t: blob.count(t) for t in PREREQ_TERMS},
    }


def new_york() -> dict:
    book = zipfile.ZipFile(io.BytesIO(fetch(NEW_YORK, expect=b"PK")))
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    sheets = {}
    for sheet in workbook.find("m:sheets", NS):
        part = target.get(sheet.get(REL), "")
        sheets[sheet.get("name")] = part[1:] if part.startswith("/") else "xl/" + part

    # Every cell value lives in the shared-string table, so one search over it
    # covers the whole workbook rather than one sheet.
    strings = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
               for si in ET.fromstring(book.read("xl/sharedStrings.xml"))]
    blob = " ".join(strings).lower()

    main = next((n for n in sheets if "all courses" in n.lower()), list(sheets)[0])
    body = ET.fromstring(book.read(sheets[main]))
    rows = [r for r in body.iter(f"{{{NS['m']}}}row")]
    if len(rows) < 2:
        raise ValueError("New York catalogue returned no rows — refusing to count that")

    header = []
    for cell in rows[0]:
        v = cell.find("m:v", NS)
        if cell.get("t") == "s" and v is not None and int(v.text) < len(strings):
            header.append(strings[int(v.text)])
    return {
        "state": "New York",
        "source": NEW_YORK,
        "format": "XLSX",
        "courses": len(rows) - 1,
        "sheets": sorted(sheets),
        "distinct_strings": len(strings),
        "fields": header,
        "prerequisite_terms": {t: blob.count(t) for t in PREREQ_TERMS},
    }


def probe(quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    measured = [texas(), new_york()]

    if not quiet:
        print("\nstatewide course directories\n")
        for m in measured:
            hits = sum(m["prerequisite_terms"].values())
            print(f"  {m['state']:12} {m['format']:5} {m['courses']:>7,} courses   "
                  f"prerequisite terms: {hits}")
        print()
        for name, _, why in BLOCKED:
            print(f"  {name:12} {'—':5} {'blocked':>7}           {why}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_state_courses\n")

    return {"retrieved_at": stamp, "measured": measured,
            "blocked": [{"state": s, "url": u, "response": r} for s, u, r in BLOCKED]}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json)
    except ValueError as exc:
        print(f"\nrefused: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"\nsource unreachable: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
