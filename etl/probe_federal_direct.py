"""Can this repo read IPEDS, CCD and College Scorecard direct — edtech-kg#43.

Every measured count here comes through the Urban Institute wrapper. #43 asked
whether the federal collections can be read at source instead, so that one
third party is not a single point of failure for the whole measured base.

**The licence half of that question is already answered and the answer moved.**
#43 was written when the wrapper's own terms were unconfirmed (#13). #101
measured them: Urban republishes under **ODC-By**, checked 2026-08-31. So this
is no longer "can we escape a licence blocker" but "is one dependency wise" —
a robustness question, which is a weaker reason and an honest one.

    python -m etl.probe_federal_direct           # reachability and size
    python -m etl.probe_federal_direct --deep    # also reconciles IPEDS (~9 MB)
    python -m etl.probe_federal_direct --json

`--deep` is separate because it downloads a year of IPEDS completions to count
what is in it. The reconciliation it produces is the finding that matters most,
and it does not need repeating on every run.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import re
import sys
import pathlib
import urllib.error
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "federal-direct-measured.json"

#: Written INTO the record by `--record`, not left in the file for a refresh
#: to delete — the sibling probes carry the same key.
RECORD_NOTE = (
    "One measured run of `python -m etl.probe_federal_direct --deep --record`, "
    "committed so docs/sources/federal-direct.md can be checked without "
    "downloading a year of IPEDS.")

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

#: One year of IPEDS completions at CIP-6. The file this repo would read if it
#: went direct, so it is the file measured rather than a smaller stand-in.
IPEDS_COMPLETIONS = "https://nces.ed.gov/ipeds/datacenter/data/C2022_A.zip"

#: What the wrapper reports for the same collection and year, and what this
#: repo publishes in `README.md`, `docs/schema.md` and `docs/sources/`.
WRAPPER_ROWS = 9_026_310

ROUTES = (
    ("IPEDS completions, direct", IPEDS_COMPLETIONS, False),
    ("CCD file index", "https://nces.ed.gov/ccd/files.asp", False),
    ("CCD data page", "https://nces.ed.gov/ccd/ccddata.asp", False),
    ("Scorecard bulk, institution",
     "https://ed-public-download.scorecard.network/downloads/"
     "Most-Recent-Cohorts-Institution_06102026.zip", False),
    ("Scorecard API", "https://api.data.gov/ed/collegescorecard/v1/"
     "schools?per_page=1", True),
    ("Urban wrapper, for comparison",
     "https://educationdata.urban.org/api/v1/college-university/ipeds/"
     "completions-cip-6/2022/", True),
)


class Unreachable(Exception):
    """A route this repo cannot read. Reported, never silently skipped."""


def _open(url: str, method: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                     method=method)
    return urllib.request.urlopen(request, timeout=60)


def reach(url: str, body_wanted: bool) -> dict:
    """Status, size and — where the status alone would mislead — why.

    A 403 from an endpoint that wants a key is a different fact from a 403 by
    an agent policy, and they look identical from the status line. The body is
    read where it can tell them apart.
    """
    method = "GET" if body_wanted else "HEAD"
    try:
        with _open(url, method) as response:
            size = response.headers.get("Content-Length")
            note = ""
            if body_wanted:
                note = response.read(400).decode("utf-8", "replace")[:200]
            return {"status": response.status,
                    "bytes": int(size) if size else None,
                    "note": note}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(400).decode("utf-8", "replace")
        except Exception:                                    # noqa: BLE001
            pass
        key_wanted = "API_KEY" in detail.upper()
        return {"status": exc.code, "bytes": None,
                "needs_a_key": key_wanted,
                "note": re.sub(r"\s+", " ", detail)[:200]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Unreachable(f"{url} did not answer ({exc})") from exc


def ipeds_shape() -> dict:
    """Download one year of completions and count what is actually in it.

    The point is not the size. It is that the wrapper's row count and the
    file's row count describe the same data in different SHAPES: IPEDS carries
    demographics as COLUMNS, and the wrapper unpivots them into rows. A reader
    comparing 300,877 with 9,026,310 without knowing that concludes the direct
    file is missing 97% of the data.
    """
    with _open(IPEDS_COMPLETIONS, "GET") as response:
        blob = response.read()

    with zipfile.ZipFile(io.BytesIO(blob)) as book:
        members = book.namelist()
        # The REVISED file is a second member, and choosing the wrong one is a
        # silent difference in every downstream figure. Named, not guessed at.
        base = [m for m in members if not m.lower().endswith("_rv.csv")]
        if len(base) != 1:
            raise Unreachable(
                f"expected one unrevised member in {IPEDS_COMPLETIONS}, "
                f"found {members}")
        with book.open(base[0]) as handle:
            stream = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8",
                                                     errors="replace"))
            stream.fieldnames = [c.lstrip("﻿") for c in stream.fieldnames]
            header = list(stream.fieldnames)
            rows = awards = 0
            for record in stream:
                rows += 1
                # FIRST MAJORS only. `MAJORNUM` 2 is a second major on the same
                # award, so summing every row counts those students twice —
                # which is how a completions total quietly overstates itself.
                if record.get("MAJORNUM") == "1":
                    try:
                        awards += int(record.get("CTOTALT") or 0)
                    except ValueError:
                        pass

    keys = [c for c in header if c in ("UNITID", "CIPCODE", "MAJORNUM", "AWLEVEL")]
    flags = [c for c in header if c.startswith("X")]
    counts = [c for c in header if c not in keys and not c.startswith("X")]
    if not counts:
        raise Unreachable("no demographic count columns found — the layout "
                          "changed and every figure below would be wrong")

    return {"download_bytes": len(blob), "members": members,
            # The number a reader thinks `wrapper_rows` is. Measured, so the
            # document can say what the row count is NOT.
            "awards_first_major": awards,
            "file_read": base[0], "rows": rows,
            "key_columns": keys, "flag_columns": len(flags),
            "count_columns": counts,
            "rows_x_counts": rows * len(counts),
            "wrapper_rows": WRAPPER_ROWS,
            "reconciles": rows * len(counts) == WRAPPER_ROWS}


def probe(deep: bool = False, quiet: bool = False) -> dict:
    routes = {}
    for label, url, body_wanted in ROUTES:
        routes[label] = {"url": url, **reach(url, body_wanted)}

    result = {"retrieved_at": datetime.date.today().isoformat(),
              "routes": routes,
              "read_or_measured": "measured",
              "wrapper_licence": "ODC-By, checked 2026-08-31 (#101) — so this "
                                 "is a robustness question, not a licence one"}
    if deep:
        result["ipeds"] = ipeds_shape()

    if not quiet:
        print("\nFederal collections, read direct — edtech-kg#43\n")
        for label, found in routes.items():
            size = (f"{found['bytes'] / 1024 / 1024:,.1f} MB"
                    if found.get("bytes") else "")
            key = "  NEEDS AN API KEY" if found.get("needs_a_key") else ""
            print(f"  {found['status']:>3}  {size:>10}  {label}{key}")

        if deep:
            shape = result["ipeds"]
            print("\n  IPEDS completions, one year, read whole\n")
            print(f"    downloaded           {shape['download_bytes'] / 1024 / 1024:>10,.1f} MB")
            print(f"    rows                 {shape['rows']:>13,}")
            print(f"    demographic columns  {len(shape['count_columns']):>13,}")
            print(f"    rows x columns       {shape['rows_x_counts']:>13,}")
            print(f"    the wrapper reports  {shape['wrapper_rows']:>13,}"
                  f"   {'<- reconciles exactly' if shape['reconciles'] else '<- DOES NOT RECONCILE'}")
            print(f"\n    So the wrapper's figure is not awards. It is the same "
                  f"{shape['rows']:,} rows\n    unpivoted across "
                  f"{len(shape['count_columns'])} demographic columns.")
        else:
            print("\n  --deep also downloads a year of IPEDS and reconciles it "
                  "against the wrapper.")
        print()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--deep", action="store_true",
                        help="download a year of IPEDS and reconcile it")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(deep=args.deep or args.record,
                       quiet=args.json or args.record)
    except Unreachable as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.record:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(
            json.dumps({"_": RECORD_NOTE, **result}, indent=2,
                       ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {RECORD.relative_to(ROOT)}")
    # `if`, not `elif`: a caller asking for both got silence on the sibling
    # probes until that was fixed.
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
