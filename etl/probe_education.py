"""Probe the public education sources — record counts, read live.

Every source figure quoted anywhere in this repo comes from this script.
Re-run it to verify them; do not hand-edit counts into the docs.

    python -m etl.probe_education                 # counts for every source
    python -m etl.probe_education --year 2020     # a different IPEDS year
    python -m etl.probe_education --json          # machine-readable

Two things make this cheap compared with the openFDA probe in
`regulatory-affairs-kg`: the Urban Institute API needs no key, and it reports a
`count` on every response, so an exact total costs one request per source
rather than a walk.

Sources it does NOT reach, and why:

  CIP-SOC crosswalk   Published by NCES as a spreadsheet, not an API. It is the
                      join the whole graph rests on, so it gets its own probe
                      once the file is mirrored somewhere citable.
  O*NET               A bulk database download rather than a queryable count.

Recording those gaps here rather than leaving the reader to wonder why the
table is shorter than the source list.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://educationdata.urban.org/api/v1"
USER_AGENT = "edtech-kg/0.1 (+https://github.com/samyama-ai/edtech-kg)"

# One request each. The path carries the year, so it is substituted rather than
# passed as a parameter — an unvalidated year would change which dataset is
# being counted rather than failing.
SOURCES = [
    ("IPEDS completions (CIP 6-digit)", "college-university/ipeds/completions-cip-6/{year}/",
     "Awards conferred, by institution x programme x award level"),
    ("IPEDS institution directory", "college-university/ipeds/directory/{year}/",
     "Colleges and universities"),
    ("CCD school directory", "schools/ccd/directory/{year}/",
     "US public schools"),
    ("CCD district directory", "school-districts/ccd/directory/{year}/",
     "US public school districts"),
]

# Not queryable through the API above. Named so the table's silence is
# explained rather than mistaken for absence.
UNPROBED = [
    ("NCES-BLS CIP-SOC crosswalk", "xlsx download",
     "The programme-to-occupation join this graph rests on"),
    ("O*NET occupation database", "bulk download",
     "Occupation attributes, skills and earnings"),
]


def fetch(path: str, attempts: int = 4) -> dict:
    """One request, with backoff on transient failures.

    A 404 is not treated as an empty answer here, unlike the openFDA probe: on
    this API it means the dataset or the year does not exist, which is a
    question about the request rather than an answer to it.
    """
    url = f"{API}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"{exc.code} on {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"unreachable: {url}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"not JSON from {url}: {exc}") from exc
    raise RuntimeError(f"giving up on {url}")


def total(payload: dict, source: str) -> int:
    """The record count, refusing anything that is not one.

    Zero is refused rather than reported. A renamed dataset or a year with no
    data answers 200 with `count: 0`, and a table row reading 0 looks like a
    measurement when it is a broken request.
    """
    if "count" not in payload:
        raise ValueError(f"{source}: response carries no `count` — the API shape has changed")
    count = payload["count"]
    if not isinstance(count, int):
        raise ValueError(f"{source}: `count` is {type(count).__name__}, not an integer")
    if count == 0:
        raise ValueError(
            f"{source}: reported 0 records. That is a wrong year or a renamed "
            f"dataset, not a real answer — refusing to publish it as a count."
        )
    return count


def probe(year: int, quiet: bool = False) -> dict:
    """Count every source. `quiet` suppresses the table so `--json` output
    parses — mixing the two made the JSON unreadable, which defeats the point
    of having it."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    for name, path, note in SOURCES:
        count = total(fetch(path.format(year=year)), name)
        results.append({"source": name, "count": count, "note": note,
                        "path": path.format(year=year)})
        if not quiet:
            print(f"  {name:36} {count:>12,}   {note}")

    if not quiet:
        print()
        for name, how, note in UNPROBED:
            print(f"  {name:36} {'— ' + how:>12}   {note}")

    return {"retrieved_at": stamp, "year": year, "api": API,
            "sources": results,
            "not_probed": [{"source": n, "access": h, "note": t} for n, h, t in UNPROBED]}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--year", type=int, default=2022,
                        help="Data year to count (default 2022, the latest complete IPEDS).")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)

    if not 1980 <= args.year <= datetime.now(timezone.utc).year:
        print(f"\n--year {args.year} is not a plausible data year", file=sys.stderr)
        return 1

    if not args.json:
        print(f"\neducation data sources — {args.year}\n")
    try:
        result = probe(args.year, quiet=args.json)
    except ValueError as exc:
        print(f"\nrefused: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"\nsource unreachable: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n  measured {result['retrieved_at']}")
        print(f"  reproduce with: python -m etl.probe_education --year {args.year}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
