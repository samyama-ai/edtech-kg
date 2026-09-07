"""Where the graph could get location from, measured rather than assumed.

edtech-kg#44 asked what "near me" needs and assumed NCES EDGE would be needed
for school and institution coordinates. It is not: the Urban Institute wrapper
this repo already reads, already cleared under ODC-By, carries `latitude` and
`longitude` on both directories.

Three things are measured here, and each was a wrong assumption first:

  * **Coverage.** Whether the coordinates are actually populated, not merely
    present as columns. Sampled at a stride for CCD, and as a CENSUS for IPEDS,
    which fits in one page.
  * **The page size the API really uses.** `per_page` is ignored above a cap —
    100 and 500 both return 10,000 rows. Computing a stride from the requested
    size gives a page past the end and a 404, which reads as the source being
    broken rather than the caller being wrong. That happened while measuring
    this, and it is recorded so it does not happen twice.
  * **Boundaries.** Coordinates answer "where is this school". They do not
    answer "which district contains this address", which needs geometry, and
    the vintage of that geometry has to match the directory year or schools are
    assigned to the wrong district silently.

Every figure this prints goes into `docs/sources/geography-measured.json`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

from etl.identity import USER_AGENT

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "geography-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_geography`. IPEDS coverage is "
               "a census; CCD coverage is a strided sample and says which "
               "pages it read.")

URBAN = "https://educationdata.urban.org/api/v1"
DIRECTORIES = {
    "ccd_schools": f"{URBAN}/schools/ccd/directory/2022/",
    "ipeds_institutions": f"{URBAN}/college-university/ipeds/directory/2022/",
}
TIGER = "https://www2.census.gov/geo/tiger/TIGER2022/UNSD/"

#: How many pages to read when the population needs more than one. Three, spread
#: across the whole result set — including the LAST, because a directory ordered
#: by state would otherwise be sampled entirely from its first few.
WANTED_PAGES = 3


class Unreachable(RuntimeError):
    """A source did not answer. Distinct from a source answering emptily."""


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


def page_size(url: str) -> dict:
    """What the API returns when asked for a given `per_page`.

    Asked rather than assumed. The requested size and the delivered size are
    different numbers here, and every stride computed from the first is wrong.
    """
    delivered = {}
    for asked in (100, 500):
        body = json.loads(get(f"{url}?per_page={asked}"))
        delivered[str(asked)] = len(body.get("results") or [])
    return delivered


def coverage(url: str, wanted_pages: int = WANTED_PAGES) -> dict:
    """How many records carry a usable coordinate, and over which pages."""
    first = json.loads(get(f"{url}?per_page=1"))
    population = first["count"]
    per_page = len(json.loads(get(f"{url}?per_page=100")).get("results") or [])
    if not per_page:
        raise Unreachable(f"{url} returned no rows for a sized request")

    last_page = max(1, -(-population // per_page))
    if last_page <= wanted_pages:
        read = list(range(1, last_page + 1))
    else:
        stride = last_page // wanted_pages
        read = sorted({1, *(min(last_page, 1 + i * stride)
                            for i in range(wanted_pages)), last_page})

    total = usable = absent = null_island = 0
    for page in read:
        for row in json.loads(get(f"{url}?page={page}")).get("results") or []:
            total += 1
            lat, lon = row.get("latitude"), row.get("longitude")
            if lat in (None, "") or lon in (None, ""):
                absent += 1
            elif abs(float(lat)) < 0.01 and abs(float(lon)) < 0.01:
                # (0, 0) is in the Atlantic. A row carrying it is not located.
                null_island += 1
            else:
                usable += 1

    return {
        "population": population,
        "rows_per_page": per_page,
        "pages_in_population": last_page,
        "pages_read": read,
        "is_census": total >= population,
        "sampled": total,
        "usable_coordinates": usable,
        "absent": absent,
        "null_island": null_island,
        "geography_columns": sorted(
            k for k in (first.get("results") or [{}])[0]
            if any(w in k.lower() for w in
                   ("lat", "lon", "zip", "county", "cbsa", "fips"))),
    }


def boundaries(url: str = TIGER) -> dict:
    """Whether school-district geometry is published, and how much of it."""
    body = get(url).decode("utf-8", "replace")
    files = sorted(set(re.findall(r"tl_(\d{4})_(\d+)_unsd\.zip", body)))
    return {
        "url": url,
        "state_files": len(files),
        "vintage": sorted({year for year, _ in files}),
    }


def probe() -> dict:
    return {
        "retrieved_at": datetime.date.today().isoformat(),
        "page_size_requested_vs_delivered": page_size(
            DIRECTORIES["ccd_schools"]),
        "directories": {name: coverage(url)
                        for name, url in DIRECTORIES.items()},
        "boundaries": boundaries(),
    }


def report(result: dict) -> None:
    asked = result["page_size_requested_vs_delivered"]
    print("  per_page asked -> delivered: " +
          ", ".join(f"{k} -> {v:,}" for k, v in asked.items()))
    print()
    for name, got in result["directories"].items():
        share = got["usable_coordinates"] / got["sampled"] if got["sampled"] else 0
        kind = "census" if got["is_census"] else f"sample, pages {got['pages_read']}"
        print(f"  {name}")
        print(f"    {got['population']:,} records over {got['pages_in_population']} "
              f"page(s) of {got['rows_per_page']:,}")
        print(f"    {got['sampled']:,} read ({kind})")
        print(f"    usable coordinates {got['usable_coordinates']:,} = {share:.1%}"
              f"  absent {got['absent']}  null-island {got['null_island']}")
    bounds = result["boundaries"]
    print()
    print(f"  TIGER school-district boundaries: {bounds['state_files']} state "
          f"files, vintage {', '.join(bounds['vintage']) or 'none found'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_geography")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = probe()
    except Unreachable as gone:
        print(f"source unreachable: {gone}", file=sys.stderr)
        return 2

    if args.record:
        # `write_record` from #171 is not on this branch. When that merges this
        # must adopt it, and its guard over every module with a module-level
        # RECORD will fail loudly if it is not — which is the right way round.
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
