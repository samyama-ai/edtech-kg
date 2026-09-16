"""Can enrolment be compared with completion? Measure the grain and find out.

Answering edtech-kg#204, split out of #8's question 4: *"which programmes have
the widest gap between who enrols and who completes?"*

The issue records the suspicion rather than the answer — that IPEDS enrolment is
"by institution and year, not by CIP programme", so the question may not be
answerable at the grain it assumes. That is a measurement, not an opinion, and
this probe takes it.

    python -m etl.probe_enrolment                  # print the finding
    python -m etl.probe_enrolment --year 2020      # a different IPEDS year
    python -m etl.probe_enrolment --record         # write the record

**What it measures, and why that is the whole question.** A comparison needs a
key both sides carry. Completions are published by `cipcode_6digit`; the
question assumes enrolment is too. So the probe reads the *fields* each
enrolment endpoint returns, not its counts — a count tells you how much data
there is, and the question is about what shape it is in.

Three things it deliberately does NOT do:

  * It does not download anything. The grain is visible in one row per endpoint,
    so a licence check and a bulk fetch would both be premature — and if the
    answer is "cannot be compared", they would never have been needed.
  * It does not treat an empty response as an absent endpoint. Asking
    `enrollment-full-time-equivalent` for `level_of_study=99` returns zero rows
    while levels 1, 2 and 3 return 5,959 each. Reported as "empty", that would
    have been a false finding about the source caused by a wrong parameter, so
    every endpoint is tried at each level it might accept before anything is
    said about it.
  * It does not stop at the endpoints whose names contain "enrollment". The
    catalogue is read in full and every path carrying `cip` is listed, so the
    claim "no enrolment endpoint is by programme" rests on the whole API rather
    than on the ones that were easy to guess.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

from etl.probe_education import API, fetch
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "enrolment-measured.json"

RECORD_NOTE = (
    "One measured run of `python -m etl.probe_enrolment --record`, committed so "
    "docs/sources/enrolment.md can be checked without re-reading the Urban "
    "catalogue and every enrolment endpoint.")

#: The IPEDS endpoints that count students rather than awards. `{level}` is
#: substituted where the path takes a level of study; the rest take none.
ENROLMENT = [
    ("fall-enrollment (race/sex)",
     "college-university/ipeds/fall-enrollment/{year}/{level}/race/sex/"),
    ("fall-enrollment (age/sex)",
     "college-university/ipeds/fall-enrollment/{year}/{level}/age/sex/"),
    ("fall-enrollment (residence)",
     "college-university/ipeds/fall-enrollment/{year}/residence/"),
    ("enrollment-headcount",
     "college-university/ipeds/enrollment-headcount/{year}/{level}/"),
    ("enrollment-full-time-equivalent",
     "college-university/ipeds/enrollment-full-time-equivalent/{year}/{level}/"),
    ("admissions-enrollment",
     "college-university/ipeds/admissions-enrollment/{year}/"),
]

#: What completions carry, for the side of the comparison that does work.
COMPLETIONS = ("completions-cip-6",
               "college-university/ipeds/completions-cip-6/{year}/")

#: Levels of study to try before calling an endpoint empty. 99 is "all levels"
#: on some endpoints and rejected by others; trying only 99 reported a populated
#: endpoint as empty.
LEVELS = [99, 1, 2, 3]


class Refused(Exception):
    """The source answered in a shape the finding cannot be stated from."""


def first_row(path_template: str, year: int) -> tuple[dict | None, int, str]:
    """One row from an endpoint, trying each level before reporting emptiness.

    Returns the row (or None), its count, and the path that produced it, so the
    record can say which request the fields came from rather than leaving a
    reader to guess which level answered.
    """
    levels = LEVELS if "{level}" in path_template else [None]
    empty_at = []
    for level in levels:
        path = path_template.format(year=year, level=level)
        payload = fetch(f"{path}?limit=1")
        count = payload.get("count")
        if count is None:
            raise Refused(f"{path}: no `count` in the response — the API shape "
                          f"has changed and this probe cannot read it")
        results = payload.get("results") or []
        if count and results:
            return results[0], count, path
        empty_at.append(level)
    return None, 0, path_template.format(year=year, level="/".join(
        str(level) for level in empty_at))


def cip_fields(row: dict | None) -> list[str]:
    """Field names that could serve as a programme key."""
    if not row:
        return []
    return sorted(name for name in row if "cip" in name.lower())


def cip_endpoints() -> list[str]:
    """Every path in the catalogue carrying `cip`, across the whole API.

    The finding is a negative one — no enrolment endpoint is by programme — and
    a negative claim made from a handful of guessed paths is worth much less
    than one made from the published list.
    """
    payload = fetch("api-endpoints/?limit=300")
    rows = payload.get("results") or []
    if not rows:
        raise Refused("the endpoint catalogue came back empty; the negative "
                      "finding below cannot be made without it")
    return sorted({row.get("endpoint_url", "") for row in rows
                   if "cip" in (row.get("endpoint_url") or "").lower()})


def measure(year: int) -> dict:
    enrolment = []
    for name, template in ENROLMENT:
        row, count, path = first_row(template, year)
        enrolment.append({
            "endpoint": name,
            "path": path,
            "rows": count,
            "fields": sorted(row) if row else [],
            "cip_fields": cip_fields(row),
        })

    row, count, path = first_row(COMPLETIONS[1], year)
    if not row:
        raise Refused(f"{COMPLETIONS[0]} returned no rows for {year}; the "
                      f"working side of the comparison must be measured too, "
                      f"or the finding is half a measurement")
    completions = {
        "endpoint": COMPLETIONS[0],
        "path": path,
        "rows": count,
        "fields": sorted(row),
        "cip_fields": cip_fields(row),
    }

    # The finding, computed rather than asserted: if any enrolment endpoint ever
    # grows a CIP field, this flips on its own and the issue reopens.
    comparable = any(source["cip_fields"] for source in enrolment)

    return {
        "note": RECORD_NOTE,
        "measured_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "year": year,
        "api": API,
        "enrolment": enrolment,
        "completions": completions,
        "cip_bearing_endpoints": cip_endpoints(),
        "enrolment_is_by_programme": comparable,
        "finding": (
            "enrolment carries a CIP field — #204 is answerable and this probe "
            "should be replaced by a loader"
            if comparable else
            "no IPEDS enrolment endpoint carries a CIP field, so enrolment "
            "cannot be compared with completions at programme grain"),
    }


def report(measured: dict) -> None:
    print(f"  IPEDS {measured['year']} — can enrolment be compared with "
          f"completion?\n")
    for source in measured["enrolment"]:
        rows = f"{source['rows']:,}" if source["rows"] else "no rows"
        key = ", ".join(source["cip_fields"]) or "none"
        print(f"  {source['endpoint']:<34}{rows:>12}  CIP field: {key}")
    done = measured["completions"]
    print(f"  {done['endpoint']:<34}{done['rows']:>12,}  CIP field: "
          f"{', '.join(done['cip_fields'])}")
    print(f"\n  paths carrying `cip` anywhere in the API:")
    for path in measured["cip_bearing_endpoints"]:
        print(f"    {path}")
    print(f"\n  {measured['finding']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_enrolment",
        description="Measure whether IPEDS enrolment can be joined to "
                    "completions at programme grain.")
    parser.add_argument("--year", type=int, default=2022)
    parser.add_argument("--record", action="store_true",
                        help=f"write {RECORD.relative_to(ROOT)}")
    args = parser.parse_args(argv)

    try:
        measured = measure(args.year)
    except (Refused, RuntimeError) as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 2

    report(measured)
    if args.record:
        write_record(RECORD, measured)
        print(f"\n  wrote {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
