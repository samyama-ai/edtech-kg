"""Fetch the national spine into `data/` — refusing rather than truncating.

    python -m etl.download_education            # the slice #23 chose
    python -m etl.download_education --check    # what would be fetched, and how big

edtech-kg#7. Three tables, all from the Urban Institute Education Data API,
already cleared under ODC-By in `docs/sources/education-data.md`:

  * **institutions** — IPEDS directory, Virginia 2022
  * **completions** — IPEDS completions by 6-digit CIP, Virginia 2022
  * the **CIP-SOC crosswalk** is not here: `etl/probe_cipsoc.py` already
    downloads and parses it, and a second downloader for one file is a second
    thing to keep in step.

**The slice is Virginia 2022**, decided in [`docs/first-load.md`](../docs/first-load.md)
and not re-argued here: PWCS is the one district loaded and it is in Virginia,
so a completions slice from any other state answers a different question.

**A short page is a failure, not a smaller dataset.** The API reports its own
`count`; a walk that ends with fewer rows than that has truncated, and every
figure downstream would understate silently. The same for an empty result: a
table that answers with nothing has not told us there is nothing.

Exit codes, because telling the two refusals apart is the point of having
them: **1** the source did not answer, or answered without a count; **3** the
walk came up short, or the cached slice does not check out. 0 otherwise.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

from etl.identity import USER_AGENT

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "education"

API = "https://educationdata.urban.org/api/v1"
YEAR = 2022
FIPS = 51            #: Virginia. See docs/first-load.md.
PER_PAGE = 10000     #: The API's own cap — measured in docs/sources/geography.md.
DELAY = 0.5

TABLES = {
    "institutions": {
        "url": f"{API}/college-university/ipeds/directory/{YEAR}/",
        "what": "one row per college — name, state, sector",
    },
    "completions": {
        "url": f"{API}/college-university/ipeds/completions-cip-6/{YEAR}/",
        "what": "awards by institution, 6-digit CIP, award level and "
                "demographic — the volume the slice exists to bound",
    },
}


#: What `main` returns, because a caller distinguishing "the walk came up
#: short" from "the source did not answer" is the entire point of refusing.
EXIT_UNREACHABLE = 1
EXIT_TRUNCATED = 3


class Unreachable(RuntimeError):
    """The API did not answer. Distinct from answering with no rows."""


class Truncated(RuntimeError):
    """The walk ended short of the count the API reported."""


def get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(DELAY)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as refused:
        raise Unreachable(f"{url}: HTTP {refused.code}") from refused
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


def walk(url: str) -> tuple[list[dict], int]:
    """Every row the endpoint holds, and the count it says it holds.

    **The `next` link is followed rather than a page number computed.**
    `docs/sources/geography.md` records what computing one costs: `per_page`
    is ignored above a cap, so a stride derived from the requested size runs
    past the end and 404s — which reads as the source being broken rather
    than the caller being wrong.
    """
    rows: list[dict] = []
    total: int | None = None
    page = f"{url}?fips={FIPS}&per_page={PER_PAGE}"
    while page:
        body = get(page)
        if total is None:
            total = body.get("count")
            if total is None:
                raise Unreachable(
                    f"{url} answered without a count, so a short walk could "
                    f"not be told from a complete one")
        batch = body.get("results")
        if batch is None:
            raise Unreachable(f"{url} answered without a results key")
        rows.extend(batch)
        page = body.get("next")
        if page and len(rows) >= total:
            # The count is reached but a `next` is still offered. Stop on the
            # count — following it would loop or duplicate, and the count is
            # what the completeness check below compares against.
            break
    return rows, total


def fetch(name: str, table: dict, force: bool = False) -> dict:
    """One table into `data/education/`, or the cached copy.

    Cached because the completions walk is 20 requests for 190,770 rows, and
    a loader under development runs many times. `--force` re-fetches.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}-{FIPS}-{YEAR}.json"
    if path.exists() and not force:
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as unreadable:
            # This file is written by this module, so a corrupt one means an
            # interrupted write or a hand-edit. Either way it is the same
            # answer as a truncated slice, and it arrived as a traceback.
            raise Truncated(
                f"{path.name}: the cached slice is not readable JSON "
                f"({unreadable}). Re-fetch it with --force.") from unreadable
        # **CHECKED ON THE READ PATH TOO.** The completeness check used to run
        # only on the fetch that wrote the file, so a truncated or hand-edited
        # slice on disk was served as trustworthy — and this module is the
        # "later reader" the stored counts exist for. A cache that skips the
        # check it was built to make possible is worse than no cache.
        if not held.get("rows"):
            raise Truncated(f"{path.name}: the cached slice holds no rows.")
        absent = [key for key in ("rows_collected", "count_reported")
                  if key not in held]
        if absent:
            # Both missing compare equal as `None`, so the check below passed
            # and `held["rows_collected"]` raised KeyError two lines later. A
            # slice carrying no counts cannot be checked at all.
            raise Truncated(
                f"{path.name}: the cached slice carries no "
                f"{' or '.join(absent)}, so its completeness cannot be "
                f"checked. Re-fetch it with --force.")
        if held.get("rows_collected") != held.get("count_reported"):
            raise Truncated(
                f"{path.name}: the cached slice reports "
                f"{held.get('count_reported')!r} rows and holds "
                f"{held.get('rows_collected')!r}. Re-fetch it with --force.")
        if len(held["rows"]) != held["rows_collected"]:
            raise Truncated(
                f"{path.name}: the cached slice says it holds "
                f"{held['rows_collected']:,} rows and carries "
                f"{len(held['rows']):,}.")
        return {**held, "from_cache": True, "path": str(path.relative_to(ROOT))}

    rows, total = walk(table["url"])

    if not rows:
        # REFUSED. A table answering with nothing has not told us there is
        # nothing — it has not answered. Writing an empty file would make
        # every count downstream a measured zero.
        raise Truncated(
            f"{name}: the API returned no rows at all for fips={FIPS}, "
            f"{YEAR}. That is not a measurement of zero.")
    if len(rows) != total:
        raise Truncated(
            f"{name}: the API reports {total:,} rows and the walk collected "
            f"{len(rows):,}. A short walk understates every figure "
            f"downstream and does so silently.")

    held = {
        "table": name,
        "url": table["url"],
        "what": table["what"],
        "fips": FIPS,
        "year": YEAR,
        "count_reported": total,
        "rows_collected": len(rows),
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%d"),
        "rows": rows,
    }
    # Written aside and moved into place. 190,770 rows is a large single
    # write, and a Ctrl-C or a full disk part-way through leaves a partial
    # file at the cache path — which the next run takes as its cache and dies
    # on, from a line that reads like a bug in the reader. A truncated
    # artefact that looks complete is the failure this whole module is about,
    # arriving through the write instead of through the walk.
    scratch = path.with_name(path.name + ".part")
    scratch.write_text(json.dumps(held), encoding="utf-8")
    os.replace(scratch, path)
    return {**held, "from_cache": False, "path": str(path.relative_to(ROOT))}


def check() -> dict:
    """What each table would cost, without fetching it.

    One request per table for its `count`, so someone can see the size of a
    walk before starting one.
    """
    sizes = {}
    for name, table in TABLES.items():
        body = get(f"{table['url']}?fips={FIPS}&per_page=1")
        total = body.get("count")
        if total is None:
            # `walk` refuses here with a message that says why; `--check`
            # formatted None with `:,` and died on a TypeError instead —
            # the same conclusion reached as a traceback.
            raise Unreachable(
                f"{table['url']} answered without a count, so the size of a "
                f"walk cannot be reported before starting one")
        sizes[name] = {
            "rows": total,
            "pages": (total + PER_PAGE - 1) // PER_PAGE if total else None,
            "cached": (CACHE / f"{name}-{FIPS}-{YEAR}.json").exists(),
        }
    return sizes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.download_education")
    parser.add_argument("--check", action="store_true",
                        help="Report what each table would cost, and fetch "
                             "nothing.")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even where a cached copy exists.")
    # `nargs="+"`, not `"*"`. With `"*"`, a bare `--only` yields `[]`, the
    # `if args.only` test is false, and it downloads EVERY table — the
    # opposite of what the flag reads as.
    parser.add_argument("--only", nargs="+", default=None,
                        choices=sorted(TABLES),
                        help="Fetch only these tables.")
    args = parser.parse_args(argv)

    try:
        if args.check:
            for name, size in check().items():
                # `pages` is None for a table reporting zero rows, and `:>3`
                # cannot format None — a zero-row table died here with a
                # TypeError instead of printing the zero.
                pages = "-" if size["pages"] is None else f"{size['pages']:,}"
                print(f"  {name:<14} {size['rows']:>9,} rows  "
                      f"{pages:>3} pages  "
                      f"{'cached' if size['cached'] else 'not cached'}")
            return 0

        for name, table in TABLES.items():
            if args.only and name not in args.only:
                continue
            held = fetch(name, table, force=args.force)
            print(f"  {name:<14} {held['rows_collected']:>9,} rows  "
                  f"{'from cache' if held['from_cache'] else 'fetched'}  "
                  f"-> {held['path']}")
    except Truncated as short:
        print(f"refusing the download: {short}", file=sys.stderr)
        return EXIT_TRUNCATED
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return EXIT_UNREACHABLE
    return 0


if __name__ == "__main__":
    sys.exit(main())
