"""What the Texas course table actually carries, and what it does not.

edtech-kg#49 recorded that the TWEDS C022 table "carries a CTE Course flag and
organises courses by career cluster", and hoped a cluster would join to SOC or
CIP — giving a course a route to an occupation with no prerequisite data at all.

Half of that is true. The flag is there. The cluster is not.

**Getting the file is the first finding.** The code-table page is a JavaScript
shell: served HTML holds no table, no rows and no code ids, so `curl` on the
page returns nothing useful. The data is behind a `DownloadAll` link the app
renders, and that link IS plain-fetchable once known — one zip, 130 CSVs. The
issue calls the table "downloadable as CSV", which is true only if you already
know this URL.

Every figure below is printed by this script. Nothing is typed.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime
import io
import json
import pathlib
import re
import sys
import urllib.request
import zipfile

from etl.identity import USER_AGENT

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "texas-cte-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_texas_cte`. Counts are over "
               "the whole published table, not a sample.")

#: The link the code-table page renders. Reached once through a browser, and
#: plain-fetchable thereafter — recorded so nobody has to render the page again.
DOWNLOAD = ("https://tealprod.tea.state.tx.us/TWEDS/103/1131/2258/0"
            "/CodeTable/DownloadAll")
COURSES = "C022.csv"

#: The values the flag actually takes. Assuming "1" or "Y" — the obvious guess —
#: counts zero CTE courses and reads as "the flag is empty", which is a wrong
#: finding rather than a failed one.
CTE_VALUES = ("H", "M")


def fetch(url: str = DOWNLOAD) -> bytes:
    # The shared agent string, not one this module wrote for itself — a source
    # that blocks us should be able to find out who we are from one place.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def measure(blob: bytes) -> dict:
    archive = zipfile.ZipFile(io.BytesIO(blob))
    tables = sorted(archive.namelist())
    if COURSES not in tables:
        raise SystemExit(f"{COURSES} is not in the download — it holds "
                         f"{len(tables)} tables")

    rows = list(csv.DictReader(io.StringIO(
        archive.read(COURSES).decode("utf-8-sig", "replace"))))
    flag = collections.Counter((r.get("CTE Course") or "").strip() for r in rows)
    cte = [r for r in rows if (r.get("CTE Course") or "").strip() in CTE_VALUES]

    # The two columns the issue expected to carry the cluster.
    populated = {
        column: sum(1 for r in rows if (r.get(column) or "").strip())
        for column in ("Subject", "Subject Area")
    }

    # A course reaches an occupation only through CIP or SOC. Searched across
    # every table, not just this one, because the join could live anywhere.
    joins = {}
    for name in tables:
        text = archive.read(name).decode("utf-8-sig", "replace")
        cip = re.findall(r"\b\d{2}\.\d{4}\b", text)
        soc = re.findall(r"\b\d{2}-\d{4}\b", text)
        if cip or soc:
            joins[name] = {"cip_shaped": len(cip), "soc_shaped": len(soc)}

    return {
        "retrieved_at": datetime.date.today().isoformat(),
        "source": DOWNLOAD,
        "tables_in_download": len(tables),
        "courses": {
            "rows": len(rows),
            "columns": list(rows[0]) if rows else [],
            "cte_flag_values": dict(flag),
            "cte_courses": len(cte),
        },
        "cluster_columns_populated": populated,
        "code_shaped_matches": joins,
    }


def report(result: dict) -> None:
    course = result["courses"]
    print(f"  TWEDS download        {result['tables_in_download']} code tables")
    print(f"  {COURSES:<21} {course['rows']:,} rows")
    print(f"  CTE flag values       {course['cte_flag_values']}")
    print(f"  CTE courses           {course['cte_courses']:,}")
    print()
    for column, n in result["cluster_columns_populated"].items():
        verdict = "populated" if n else "EMPTY on every row"
        print(f"  {column:<21} {verdict}")
    print()
    if result["code_shaped_matches"]:
        print("  code-shaped matches (checked by hand — statute refs, not codes):")
        for name, counts in result["code_shaped_matches"].items():
            print(f"    {name:<12} {counts}")
    else:
        print("  no CIP- or SOC-shaped codes anywhere in the download")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_texas_cte")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = measure(fetch())
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        print(f"source unreachable: {gone}", file=sys.stderr)
        return 2
    except zipfile.BadZipFile as bad:
        print(f"the download is not a zip: {bad}", file=sys.stderr)
        return 3

    if args.record:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps({"_": RECORD_NOTE, **result}, indent=2,
                                     ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(f"wrote {RECORD.relative_to(ROOT)}")
    elif args.json:
        print(json.dumps(result, indent=2))
    else:
        report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
