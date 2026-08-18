"""Probe the NCES-BLS CIP-SOC crosswalk — the join this whole graph rests on.

`probe_education.py` counts the four sources reachable through an API. This one
covers the fifth, and the most important: the crosswalk that maps a degree
programme to the occupations it leads to. Every answerable question in
`docs/questions.md` traverses it.

It is published as a spreadsheet rather than an API, which is why it needed its
own probe — and why its figures were the last hand-counted numbers in this repo.

    python -m etl.probe_cipsoc                # counts, from the file
    python -m etl.probe_cipsoc --json         # machine-readable
    python -m etl.probe_cipsoc --download     # fetch it first

**No third-party dependency.** An .xlsx is a zip of XML, and reading two sheets
out of one is about forty lines of standard library. Adding openpyxl to count
rows would make the probe harder to run than the thing it measures.

What the crosswalk is, and what it is not: NCES and the Bureau of Labor
Statistics say themselves that it reflects **expert judgment about what a
programme prepares a student for** — not measured employment outcomes. That
caveat belongs in every answer derived from it.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE_URL = "https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx"
LANDING_PAGE = "https://nces.ed.gov/ipeds/cipcode/post3.aspx?y=56"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOCAL = DATA_DIR / "CIP2020_SOC2018_Crosswalk.xlsx"
USER_AGENT = "edtech-kg/0.1 (+https://github.com/samyama-ai/edtech-kg)"

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def download(path: Path | None = None) -> Path:
    """Fetch the workbook from NCES. Not committed — data/ is gitignored."""
    path = path or LOCAL
    path.parent.mkdir(exist_ok=True)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"could not fetch {SOURCE_URL}: {exc}") from exc
    if not payload.startswith(b"PK"):
        raise ValueError(
            f"{SOURCE_URL} did not return a workbook — got {len(payload)} bytes "
            f"starting {payload[:16]!r}. NCES may have moved the file; check "
            f"{LANDING_PAGE}"
        )
    path.write_bytes(payload)
    return path


def sheets(book: zipfile.ZipFile) -> dict[str, str]:
    """Sheet name -> the XML part holding it.

    Resolved through the relationship file rather than assumed to be
    `sheet1.xml`, `sheet2.xml` in order — the order in the workbook and the
    filenames on disk are not required to agree, and silently reading the wrong
    sheet would produce a plausible count of the wrong thing.
    """
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels}
    out = {}
    for sheet in workbook.find("m:sheets", NS):
        part = target.get(sheet.get(REL), "")
        out[sheet.get("name")] = "xl/" + part.lstrip("/")
    return out


def rows(book: zipfile.ZipFile, part: str) -> list[list[str]]:
    """Every row of one sheet, as strings.

    Values live either inline or in a shared-string table, so both forms are
    resolved. Blank trailing rows are dropped — Excel writes them and counting
    them would inflate every figure here.
    """
    shared: list[str] = []
    if "xl/sharedStrings.xml" in book.namelist():
        table = ET.fromstring(book.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
                  for si in table]

    sheet = ET.fromstring(book.read(part))
    out = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        values = []
        for cell in row:
            text = ""
            value = cell.find("m:v", NS)
            if cell.get("t") == "s" and value is not None:
                index = int(value.text)
                text = shared[index] if index < len(shared) else ""
            elif cell.get("t") == "inlineStr":
                inline = cell.find("m:is", NS)
                text = "".join(t.text or "" for t in inline.iter(f"{{{NS['m']}}}t")) if inline is not None else ""
            elif value is not None:
                text = value.text or ""
            values.append(text.strip())
        if any(values):
            out.append(values)
    return out


def is_code_header(text: str, name: str) -> bool:
    """Does this cell name a code column, rather than merely mention the word?

    The distinction matters. These sheets open with a title like
    "2020 CIP / 2018 SOC Crosswalk", which contains both words — matching on
    "CIP" alone finds the title and then reads the row below it as data, so
    every count comes out one too high and nothing errors. The real headings
    are `CIP2020Code` and `SOC2018Code`, so the cell has to carry the word
    *and* "code".
    """
    flat = "".join(c for c in text.lower() if c.isalnum())
    return name.lower() in flat and "code" in flat


def column(table: list[list[str]], header_row: int, name: str) -> list[str]:
    """One named column's values, matched on the header rather than position.

    Column order is not a contract. Matching by name means a reordered file
    fails loudly instead of counting the wrong column.
    """
    for i, heading in enumerate(table[header_row]):
        if is_code_header(heading, name):
            return [r[i] for r in table[header_row + 1:] if i < len(r) and r[i]]
    raise ValueError(
        f"no {name} code column — header row reads {table[header_row]}. "
        f"The workbook layout has changed; the counts cannot be trusted."
    )


def find_header(table: list[list[str]], name: str) -> int:
    """The row carrying the column headings, wherever NCES put it below the title."""
    for i, row in enumerate(table[:12]):
        if any(is_code_header(c, name) for c in row):
            return i
    raise ValueError(
        f"no header row naming a {name} code column in the first 12 rows — "
        f"first rows read {table[:3]}"
    )


def probe(path: Path | None = None, quiet: bool = False) -> dict:
    # Resolved at call time, not bound as a default at import: a default
    # argument freezes the value, so LOCAL could not be redirected — by a test,
    # or by anything else wanting the file somewhere other than ./data.
    path = path or LOCAL
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m etl.probe_cipsoc --download` "
            f"first — the workbook is not committed, per the KG-repo convention."
        )
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    book = zipfile.ZipFile(path)
    parts = sheets(book)

    required = ["CIP-SOC", "Unmatched CIP Codes", "Unmatched SOC Codes"]
    missing = [s for s in required if s not in parts]
    if missing:
        raise ValueError(
            f"workbook is missing {missing}. It has {sorted(parts)}. NCES has "
            f"changed the layout — check {LANDING_PAGE} before trusting anything."
        )

    crosswalk = rows(book, parts["CIP-SOC"])
    head = find_header(crosswalk, "CIP")
    cip = column(crosswalk, head, "CIP")
    soc = column(crosswalk, head, "SOC")

    unmatched_cip = rows(book, parts["Unmatched CIP Codes"])
    unmatched_soc = rows(book, parts["Unmatched SOC Codes"])
    ucip = column(unmatched_cip, find_header(unmatched_cip, "CIP"), "CIP")
    usoc = column(unmatched_soc, find_header(unmatched_soc, "SOC"), "SOC")

    result = {
        "retrieved_at": stamp,
        "source": SOURCE_URL,
        "landing_page": LANDING_PAGE,
        "file_bytes": path.stat().st_size,
        "mappings": len(cip),
        "distinct_cip": len(set(cip)),
        "distinct_soc": len(set(soc)),
        "unmatched_cip": len(set(ucip)),
        "unmatched_soc": len(set(usoc)),
        "sheets": sorted(parts),
    }
    if result["mappings"] == 0:
        raise ValueError("the CIP-SOC sheet parsed to zero rows — refusing to report that as a count")

    if not quiet:
        print(f"\nNCES-BLS CIP-SOC crosswalk\n")
        print(f"  programme-to-occupation mappings   {result['mappings']:>8,}")
        print(f"  distinct CIP codes (programmes)    {result['distinct_cip']:>8,}")
        print(f"  distinct SOC codes (occupations)   {result['distinct_soc']:>8,}")
        print(f"  CIP codes with no occupation       {result['unmatched_cip']:>8,}")
        print(f"  SOC codes with no programme        {result['unmatched_soc']:>8,}")
        print(f"\n  measured {stamp}")
        print(f"  source   {SOURCE_URL}")
        print(f"  reproduce with: python -m etl.probe_cipsoc\n")
    return result


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--download", action="store_true", help="Fetch the workbook first.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)

    try:
        if args.download:
            path = download()
            if not args.json:
                print(f"\n  downloaded {path.stat().st_size / 1e3:.0f} KB -> {path}")
        result = probe(quiet=args.json)
    except FileNotFoundError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
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
