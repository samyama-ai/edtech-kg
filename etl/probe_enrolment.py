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
  * It does not stop at the first level that answers. Asking
    `enrollment-full-time-equivalent` for `level_of_study=99` returns zero rows
    while other levels return data, so a single request would report a populated
    endpoint as empty. **Every level is requested and every count recorded**,
    rather than returning on the first that answers — otherwise the record would
    carry a per-level claim that was never measured.
  * It does not stop at the endpoints whose names contain "enrollment". The
    catalogue is read in full and every path carrying `cip` is listed, so the
    claim "no enrolment endpoint is by programme" rests on the whole API rather
    than on the ones that were easy to guess. A truncated catalogue would make
    that claim from partial evidence, so a short read is refused rather than
    reported.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from datetime import datetime, timezone

from etl.probe_education import API, fetch
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "enrolment-measured.json"

RECORD_NOTE = (
    "One measured run of `python -m etl.probe_enrolment --record`, committed so "
    "docs/sources/enrolment.md can be checked without re-reading the Urban "
    "catalogue and every enrolment endpoint at every level.")

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

#: Levels of study to request. 99 is "all levels" on some endpoints and rejected
#: by others, so every one of these is asked and answered for in the record.
LEVELS = [99, 1, 2, 3]

#: Page size for the endpoint catalogue. The read is refused if the reported
#: total exceeds what came back — see `cip_endpoints`.
CATALOGUE_LIMIT = 300


class Refused(Exception):
    """The source answered in a shape the finding cannot be stated from."""


#: `fetch` raises RuntimeError("404 on <url>") for anything it will not retry.
#: Matching on that text is a coupling to a sibling module's message, so it is
#: narrow and tested: a 404 means "this endpoint does not publish this level or
#: year", which is an answer, while every other error still fails loudly.
NOT_PUBLISHED = re.compile(r"^404 on ")


def read_endpoint(name: str, template: str, year: int) -> dict:
    """Every level of one endpoint, with the count each level returned.

    No early return. Stopping at the first level that answers would leave the
    record asserting per-level figures that were never requested — and a
    per-level claim is exactly what this probe exists to make, because one
    endpoint is empty at the level the others accept.

    `fields_from` names the request the fields were read out of, and is null
    when no level answered. It is never synthesised: a path in the record is a
    URL a reader can paste, or it is absent.
    """
    levels = LEVELS if "{level}" in template else [None]
    attempts: list[dict] = []
    fields: list[str] = []
    cip: set[str] = set()
    fields_from: str | None = None
    rows_where_read = 0

    for level in levels:
        path = template.format(year=year, level=level)
        try:
            payload = fetch(f"{path}?limit=1")
        except RuntimeError as error:
            if not NOT_PUBLISHED.match(str(error)):
                raise
            # A level this endpoint does not publish. Recorded and stepped over:
            # aborting here would throw away seventeen successful requests
            # because the eighteenth asked for a year an endpoint has no data
            # for, which is the opposite of "every level is asked and answered
            # for".
            attempts.append({"level": level, "path": path,
                             "rows": None, "http": 404})
            continue
        count = payload.get("count")
        if count is None:
            raise Refused(f"{path}: no `count` in the response — the API shape "
                          f"has changed and this probe cannot read it")
        results = payload.get("results") or []
        attempts.append({"level": level, "path": path, "rows": count})
        if count and results:
            row = results[0]
            # Read from every level that answers, not just the first: a CIP
            # field appearing at one level only is still a CIP field, and the
            # finding must not depend on which level was asked first.
            cip.update(field for field in row if "cip" in field.lower())
            if fields_from is None:
                fields = sorted(row)
                fields_from = path
                rows_where_read = count

    return {
        "endpoint": name,
        "levels": attempts,
        "paths_tried": [attempt["path"] for attempt in attempts],
        "fields_from": fields_from,
        # Named for what it is. Next to a `levels` array a bare `rows` reads as
        # a total, and it is not one: it is the count at the level the fields
        # were read from.
        "rows_at_fields_from": rows_where_read,
        "fields": fields,
        "cip_fields": sorted(cip),
        # The distinction the finding depends on. An endpoint that answered with
        # rows and carried no CIP field is evidence; one that returned nothing
        # at any level is an absence of data, and saying "no CIP field" of it
        # would be claiming something was observed when nothing was.
        "fields_seen": fields_from is not None,
    }


def cip_endpoints() -> list[str]:
    """Every path in the catalogue carrying `cip`, across the whole API.

    The finding is a negative one — no enrolment endpoint is by programme — and
    a negative claim made from a handful of guessed paths is worth much less
    than one made from the published list. Which means a *truncated* list is
    worse than useless: it would keep reporting the same ten paths from a page
    that no longer holds all of them, with nothing to say it had been cut.
    """
    payload = fetch(f"api-endpoints/?limit={CATALOGUE_LIMIT}")
    rows = payload.get("results") or []
    if not rows:
        raise Refused("the endpoint catalogue came back empty; the negative "
                      "finding below cannot be made without it")
    total = payload.get("count")
    if not isinstance(total, int):
        raise Refused(
            f"the endpoint catalogue reported no usable `count` ({total!r}), "
            f"so a truncated page cannot be told from a complete one — and the "
            f"finding rests on having seen the whole list")
    if total > len(rows):
        raise Refused(
            f"the endpoint catalogue reports {total} entries and returned "
            f"{len(rows)}. The finding rests on having seen all of them — "
            f"raise CATALOGUE_LIMIT and re-run rather than publishing a claim "
            f"made from a truncated page")
    return sorted({row.get("endpoint_url", "") for row in rows
                   if "cip" in (row.get("endpoint_url") or "").lower()})


def measure(year: int) -> dict:
    enrolment = [read_endpoint(name, template, year)
                 for name, template in ENROLMENT]

    completions = read_endpoint(COMPLETIONS[0], COMPLETIONS[1], year)
    if not completions["fields_from"]:
        raise Refused(f"{COMPLETIONS[0]} returned no rows for {year}; the "
                      f"working side of the comparison must be measured too, "
                      f"or the finding is half a measurement")

    # The finding, computed rather than asserted: if any enrolment endpoint ever
    # grows a CIP field, this flips on its own and the issue reopens.
    observed = [source for source in enrolment if source["fields_seen"]]
    comparable = any(source["cip_fields"] for source in observed)

    return {
        "note": RECORD_NOTE,
        "measured_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "year": year,
        "api": API,
        "enrolment": enrolment,
        "completions": completions,
        "cip_bearing_endpoints": cip_endpoints(),
        # What the finding rests on, and what it does not. An endpoint with no
        # rows contributes nothing either way.
        "endpoints_observed": [source["endpoint"] for source in observed],
        "endpoints_without_rows": [source["endpoint"] for source in enrolment
                                   if not source["fields_seen"]],
        "requests": sum(len(source["paths_tried"]) for source in enrolment)
                    + len(completions["paths_tried"]) + 1,
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
    for source in measured["enrolment"] + [measured["completions"]]:
        counts = ", ".join(
            (f"{attempt['level']}:" if attempt["level"] is not None else "")
            + ("404" if attempt["rows"] is None else f"{attempt['rows']:,}")
            for attempt in source["levels"])
        key = (", ".join(source["cip_fields"]) or "none") if source["fields_seen"] \
            else "not measured — no rows"
        print(f"  {source['endpoint']:<34}{counts:<42}CIP field: {key}")
    print("\n  paths carrying `cip` anywhere in the API:")
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
