"""Probe the statewide course directories — counts, and whether prerequisites exist.

The question #40 asked: does any state publish a course list carrying
prerequisites? Two of the five checked are machine-readable and neither does.
This script is how that was established, so the answer can be re-derived rather
than believed.

    python -m etl.probe_state_courses          # the table
    python -m etl.probe_state_courses --json   # machine-readable

**Nothing here is a stored constant.** Every state in `SOURCES` is fetched on
every run, including the three that have been refusing — their status is
whatever the server says today, not what it said when this was written. That
matters for #50: re-checking whether Florida, Virginia and California have
opened up is `python -m etl.probe_state_courses`, not a manual round of curl.

**No third-party dependency**, as with the other probes: the Texas file is CSV
and the New York one is a zip of XML.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone

from etl.identity import USER_AGENT

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

TEXAS = ("https://tealprod.tea.state.tx.us/TWEDS/66/0/0/0/"
         "CodeTable/DownloadSingle/7999%7CC022")
NEW_YORK = "https://www.p12.nysed.gov/irs/courseCatalog/sced-course-codes-2024-25.xlsx"

# Fetched on every run. No status is stored here — see the module docstring.
UNPARSED = {
    "Florida": "https://www.fldoe.org/policy/articulation/ccd/",
    "Virginia": ("https://www.doe.virginia.gov/data-policy-funding/data-reports/"
                 "data-collection/master-schedule-collection/msc-code-values"),
    "California": "https://www.cde.ca.gov/ds/sp/cl/systemdocs.asp",
}

# A prerequisite in a course record would say so in one of these ways.
STRONG_TERMS = ("prerequisit", "pre-requisit", "must have completed", "before taking")

# These also appear in ordinary course descriptions — "prior to the exam",
# "successful completion of the unit". Counted, reported, and deliberately kept
# out of the verdict, because summing them with the strong terms would make the
# printed table contradict the conclusion the document draws from it.
WEAK_TERMS = ("prior to", "successful completion")

# Columns TEA's C022 table has carried throughout. Their absence means the
# response is not the code table — a 200 carrying a maintenance page parses as
# CSV perfectly well and would otherwise be counted as courses.
TEXAS_COLUMNS = ("code", "translation")

# The sheet the course count comes from. If a future edition renames it, the
# probe refuses rather than counting whichever sheet happens to be first.
NY_COURSE_SHEET = "all courses"


class MalformedSource(Exception):
    """The source was reachable but did not parse.

    Distinct from a refusal (we will not report a figure we cannot vouch for)
    and from an unreachable source. Reporting a parse failure as "refused"
    puts a broken file in the same category as an honest zero.
    """


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


def attempt(state: str, url: str) -> dict:
    """Ask, and record what the server actually said today.

    Returns the observed status rather than a remembered one, so a state that
    starts serving shows up on the next run instead of staying `403` forever.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            final = response.geturl()
            return {"state": state, "url": url, "status": response.status,
                    "redirected_to": final if final != url else None,
                    "bytes": len(response.read())}
    except urllib.error.HTTPError as exc:
        reason = str(exc.reason)
        # urlopen follows redirects, so a 3xx only surfaces here when it gave up —
        # in practice a loop, which is what a firewall bouncing the request looks
        # like. Worth distinguishing from an ordinary redirect.
        looping = 300 <= exc.code < 400 and "infinite loop" in reason.lower()
        return {"state": state, "url": url, "status": exc.code,
                "reason": reason.splitlines()[0], "redirect_loop": looping or None}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"state": state, "url": url, "status": None, "reason": str(exc)}


def term_counts(blob: str) -> dict:
    return {"strong": {t: blob.count(t) for t in STRONG_TERMS},
            "weak": {t: blob.count(t) for t in WEAK_TERMS}}


def texas() -> dict:
    rows = list(csv.reader(io.StringIO(fetch(TEXAS).decode("utf-8-sig", "replace"))))
    if len(rows) < 2:
        raise ValueError("Texas C022 returned no rows — refusing to report that as a count")
    header = [c.strip().lower() for c in rows[0]]
    missing = [c for c in TEXAS_COLUMNS if not any(c in h for h in header)]
    if missing:
        raise ValueError(
            f"Texas C022 is missing the {missing} column(s) — got {rows[0]!r}. "
            f"An error page served with a 200 parses as CSV and would be counted "
            f"as courses; refusing to report a figure from it."
        )
    blob = " ".join(" ".join(r) for r in rows).lower()
    return {
        "state": "Texas",
        "source": TEXAS,
        "format": "CSV",
        "courses": len(rows) - 1,
        "counted_from": "the single CSV table",
        "fields": rows[0],
        "prerequisite_terms": term_counts(blob),
    }


def _cell_text(cell, strings: list[str]) -> str:
    """A cell's display text, whatever storage form it uses."""
    if cell.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
    v = cell.find("m:v", NS)
    if v is None or v.text is None:
        return ""
    if cell.get("t") == "s":
        try:
            index = int(v.text)
        except ValueError as exc:
            raise MalformedSource(f"shared-string index {v.text!r} is not a number") from exc
        if not 0 <= index < len(strings):
            raise MalformedSource(f"shared-string index {index} is outside the table")
        return strings[index]
    return v.text


def new_york() -> dict:
    payload = fetch(NEW_YORK, expect=b"PK")
    try:
        # A truncated download starts with PK and is still not a workbook, so the
        # magic-byte check above is necessary and not sufficient.
        book = zipfile.ZipFile(io.BytesIO(payload))
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        strings = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
                   for si in ET.fromstring(book.read("xl/sharedStrings.xml"))]
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise MalformedSource(
            f"the New York workbook is not readable ({type(exc).__name__}: {exc})") from exc

    target = {r.get("Id"): r.get("Target") for r in rels}
    sheets = {}
    for sheet in workbook.find("m:sheets", NS):
        part = target.get(sheet.get(REL), "")
        sheets[sheet.get("name")] = part[1:] if part.startswith("/") else "xl/" + part

    # Every cell value lives in the shared-string table, so one search over it
    # covers the whole workbook rather than one sheet.
    blob = " ".join(strings).lower()

    def data_rows(path):
        body = ET.fromstring(book.read(path))
        # Trailing rows carrying only styling have no value cells. Counting them
        # would overstate the total in exactly the silent way the header row did.
        return [r for r in body.iter(f"{{{NS['m']}}}row")
                if any(c.find("m:v", NS) is not None or c.find("m:is", NS) is not None
                       for c in r)]

    per_sheet = {name: max(len(data_rows(path)) - 1, 0) for name, path in sheets.items()}

    main = next((n for n in sheets if NY_COURSE_SHEET in n.lower()), None)
    if main is None:
        raise ValueError(
            f"no sheet named like {NY_COURSE_SHEET!r} in {sorted(sheets)} — refusing to "
            f"count an arbitrary sheet. If the catalogue was restructured, "
            f"NY_COURSE_SHEET needs updating and the figure re-checked."
        )
    rows = data_rows(sheets[main])
    if len(rows) < 2:
        raise ValueError(f"New York sheet {main!r} has no data rows — refusing to count that")

    return {
        "state": "New York",
        "source": NEW_YORK,
        "format": "XLSX",
        # The course count is one sheet. The others track edition-to-edition
        # changes and are not additional courses — summing them would double-count.
        "courses": len(rows) - 1,
        "counted_from": f"the {main!r} sheet only",
        "rows_per_sheet": per_sheet,
        "other_sheets_are": "change tracking, not additional courses",
        "distinct_strings": len(strings),
        "fields": [t for t in (_cell_text(c, strings) for c in rows[0]) if t],
        "prerequisite_terms": term_counts(blob),
    }


def probe(quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    measured = [texas(), new_york()]
    unparsed = [attempt(s, u) for s, u in UNPARSED.items()]

    if not quiet:
        print("\nstatewide course directories\n")
        for m in measured:
            strong = sum(m["prerequisite_terms"]["strong"].values())
            weak = sum(m["prerequisite_terms"]["weak"].values())
            print(f"  {m['state']:12} {m['format']:5} {m['courses']:>7,} courses   "
                  f"prerequisite terms: {strong}   (weak, prose: {weak})")
        print()
        for a in unparsed:
            status = a["status"] if a["status"] is not None else "no response"
            note = f" → {a['redirected_to']}" if a.get("redirected_to") else ""
            print(f"  {a['state']:12} {'—':5} {'not parsed':>7}   {status}{note}")
        print(f"\n  the verdict counts strong terms only; weak ones "
              f"({', '.join(WEAK_TERMS)}) occur in ordinary prose")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_state_courses\n")

    return {"retrieved_at": stamp, "measured": measured, "unparsed": unparsed,
            "strong_terms": list(STRONG_TERMS), "weak_terms": list(WEAK_TERMS)}


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
    except MalformedSource as exc:
        print(f"\nsource malformed: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
