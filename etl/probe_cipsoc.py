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

**No third-party dependency.** An .xlsx is a zip of XML, and reading the three
sheets this needs is about sixty lines of standard library. Adding openpyxl to count
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
    path.parent.mkdir(parents=True, exist_ok=True)
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
        # OPC allows an absolute part name, and some writers emit
        # Target="/xl/worksheets/sheet1.xml". Prefixing that unconditionally
        # gave "xl/xl/..." and a KeyError out of read() — a traceback rather
        # than a message, since main() catches no KeyError.
        out[sheet.get("name")] = part[1:] if part.startswith("/") else "xl/" + part
    return out


def col_index(ref: str) -> int:
    """`C5` -> 2. The column letters of a cell reference, as a 0-based index."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def rows(book: zipfile.ZipFile, part: str) -> list[list[str]]:
    """Every row of one sheet, as strings, placed by cell reference.

    Values live either inline or in a shared-string table, so both forms are
    resolved. Blank trailing rows are dropped — Excel writes them and counting
    them would inflate every figure here.

    **Cells are placed by their `r` attribute, not by document order.** Excel
    omits an empty cell entirely rather than writing a blank one, so a row whose
    title is blank arrives as `<c r="A5">…</c><c r="C5">…</c>`. Appending in
    order would put the SOC code in the column the header calls CIP2020Title,
    and every count after that is a plausible count of the wrong thing — with no
    error anywhere.
    """
    shared: list[str] = []
    if "xl/sharedStrings.xml" in book.namelist():
        table = ET.fromstring(book.read("xl/sharedStrings.xml"))
        shared = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
                  for si in table]

    sheet = ET.fromstring(book.read(part))
    out = []
    for row in sheet.iter(f"{{{NS['m']}}}row"):
        placed: dict[int, str] = {}
        for position, cell in enumerate(row):
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
            ref = cell.get("r")
            column = col_index(ref) if ref else position
            placed[max(column, 0)] = text.strip()
        if any(placed.values()):
            width = max(placed) + 1
            out.append([placed.get(i, "") for i in range(width)])
    return out


def is_code_header(text: str, name: str) -> bool:
    """Does this cell name a code column, rather than merely mention the word?

    The distinction matters, and it caught this function out twice.

    These sheets open with a title. The `CIP-SOC` one reads "2020 CIP / 2018 SOC
    Crosswalk", so matching on "CIP" alone found the title and read the row below
    it as data — every count one too high, nothing erroring.

    Requiring "code" as well was not enough either: the other two sheets are
    named **"Unmatched CIP Codes"** and **"Unmatched SOC Codes"**, and a sheet
    that repeats its own name in A1 — the layout `CIP-SOC` itself uses —
    contains both the name and "code". Reproduced: `unmatched_cip` came back 2
    instead of 1.

    So the cell must *end* with "code". `cip2020code` does; `unmatchedcipcodes`
    ends with "codes" and does not. That is what distinguishes a column heading
    from a sheet title naming the same thing.
    """
    flat = "".join(c for c in text.lower() if c.isalnum())
    return name.lower() in flat and flat.endswith("code")


def column_at(table: list[list[str]], header_row: int, name: str) -> int:
    """The index of a named code column, matched on the header not position.

    Column order is not a contract. Matching by name means a reordered file
    fails loudly instead of counting the wrong column.
    """
    for i, heading in enumerate(table[header_row]):
        if is_code_header(heading, name):
            return i
    raise ValueError(
        f"no {name} code column — header row reads {table[header_row]}. "
        f"The workbook layout has changed; the counts cannot be trusted."
    )


def column(table: list[list[str]], header_row: int, name: str) -> list[str]:
    """One named column's non-empty values."""
    i = column_at(table, header_row, name)
    return [r[i] for r in table[header_row + 1:] if i < len(r) and r[i]]


def pairs(table: list[list[str]], header_row: int) -> tuple[list[tuple[str, str]], int]:
    """Complete (CIP, SOC) pairs, and how many rows were incomplete.

    Read together, per row, rather than as two independently filtered columns.
    Filtering each side separately means a row blank on one side still counts
    toward the other, so "mappings" silently becomes "rows carrying a CIP code"
    rather than "programme-to-occupation pairs". A blank on either side is a
    row that maps nothing, and it should be visible rather than absorbed.
    """
    ci = column_at(table, header_row, "CIP")
    si = column_at(table, header_row, "SOC")
    complete, partial = [], 0
    for row in table[header_row + 1:]:
        cip = row[ci] if ci < len(row) else ""
        soc = row[si] if si < len(row) else ""
        if cip and soc:
            complete.append((cip, soc))
        elif cip or soc:
            partial += 1
    return complete, partial


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
    try:
        book = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        # A truncated download, or an HTML error page saved under this name.
        # `download()` guards the fetch; this guards a file that arrived some
        # other way, so the reader gets the same clear message either time.
        raise ValueError(
            f"{path} is not a workbook ({exc}). NCES may have moved the file — "
            f"check {LANDING_PAGE}, then re-run with --download."
        ) from exc
    with book:
        return measure(book, path, stamp, quiet)


def measure(book: zipfile.ZipFile, path: Path, stamp: str, quiet: bool) -> dict:
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
    mapped, partial = pairs(crosswalk, head)
    cip = [c for c, _ in mapped]
    soc = [s for _, s in mapped]

    unmatched_cip = rows(book, parts["Unmatched CIP Codes"])
    unmatched_soc = rows(book, parts["Unmatched SOC Codes"])
    ucip = column(unmatched_cip, find_header(unmatched_cip, "CIP"), "CIP")
    usoc = column(unmatched_soc, find_header(unmatched_soc, "SOC"), "SOC")

    result = {
        "retrieved_at": stamp,
        "source": SOURCE_URL,
        "landing_page": LANDING_PAGE,
        "file_bytes": path.stat().st_size,
        "mappings": len(mapped),
        "incomplete_rows": partial,
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
