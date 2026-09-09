"""How much the Completion key loses if `majornum` is left out of it.

edtech-kg#7. The schema's `Completion` key was five parts — institution, CIP,
award level, demographic, year — and IPEDS publishes a sixth. Two rows
differing only by `majornum` are two real completions, and under the
five-part key they merge into one node and one award count is lost.

**Nothing fails when that happens.** The load reports fewer nodes than rows,
which is exactly what a MERGE is supposed to do, so the loss is invisible in
every figure the loader prints.

The figures for it were measured once by hand and then written into
`schema/edtech_kg.cypher`, `etl/load_education.py` and
`docs/national-spine.md` — three copies of a number with no run behind it,
which is the failure this repo has had most often. This is the run.

    python -m etl.probe_completion_key
    python -m etl.probe_completion_key --record

No network: it reads the slice `etl/download_education.py` already cached.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

from etl.load_education import CACHE, FIPS, YEAR, held
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "completion-key-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.probe_completion_key --record` over the "
    "cached slice. `groups_losing_a_count` is the figure that matters: "
    "groups where the five-part key merges rows AND more than one of them "
    "carries a non-zero award, so a real count disappears. The larger "
    "`groups_with_more_than_one_majornum` includes merges where every other "
    "row is a zero and nothing is lost.")

#: The five-part key, spelled as the schema spelled it before the fix.
FIVE = ("unitid", "cipcode_6digit", "award_level", "race", "sex")


def measure() -> dict:
    rows = held("completions")["rows"]

    by_five: dict[tuple, list] = collections.defaultdict(list)
    for row in rows:
        by_five[tuple(row[field] for field in FIVE)].append(row)

    merged = {key: group for key, group in by_five.items() if len(group) > 1}
    many_majors = {
        key: group for key, group in merged.items()
        if len({row["majornum"] for row in group}) > 1}
    losing = {
        key: group for key, group in many_majors.items()
        if sum(1 for row in group if (row.get("awards_6digit") or 0) > 0) > 1}

    return {
        "_": RECORD_NOTE,
        "fips": FIPS, "year": YEAR,
        "rows": len(rows),
        "distinct_five_part_keys": len(by_five),
        "distinct_six_part_keys": len({
            tuple(row[field] for field in FIVE) + (row["majornum"],)
            for row in rows}),
        "groups_the_five_part_key_merges": len(merged),
        "groups_with_more_than_one_majornum": len(many_majors),
        "groups_losing_a_count": len(losing),
        "awards_lost": sum(
            sum(sorted((row.get("awards_6digit") or 0) for row in group)[:-1])
            for group in losing.values()),
    }


def report(found: dict) -> None:
    print(f"  {found['rows']:,} rows, fips={found['fips']} {found['year']}")
    print(f"  {found['distinct_six_part_keys']:,} distinct six-part keys, "
          f"{found['distinct_five_part_keys']:,} five-part")
    print(f"  the five-part key merges "
          f"{found['groups_the_five_part_key_merges']:,} groups")
    print(f"    of those, {found['groups_with_more_than_one_majornum']:,} "
          f"carry more than one majornum")
    print(f"    of those, {found['groups_losing_a_count']:,} have more than "
          f"one NON-ZERO award — these lose data")
    print(f"  awards that disappear: {found['awards_lost']:,}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_completion_key",
        description=__doc__.strip().splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.json and args.record:
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2
    try:
        found = measure()
    except Exception as gone:                       # noqa: BLE001
        print(f"{gone}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(found, indent=2))
        return 0
    report(found)
    if args.record:
        if not found["rows"]:
            # A slice with no rows measures nothing, and writing that over a
            # real measurement is how a record of something becomes a record
            # of nothing.
            print(f"refusing to --record: {CACHE} held no rows.",
                  file=sys.stderr)
            return 3
        write_record(RECORD, found)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
