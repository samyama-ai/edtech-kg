"""Can an edge from a high-school course to college credit be sourced at all?

    python -m etl.probe_articulation --record

edtech-kg#42. The graph has two tiers that do not touch — high-school courses
on one side, CIP/IPEDS programmes on the other — and the bridge between them
is **credit that carries**. The issue expects the answer to be no and says a
no is worth as much as a yes, because it would mean Q4 should be re-rated in
`docs/questions.md` rather than left implying a route nobody can compute.

The answer is **not** a flat no, and the difference is granularity:

  * **At institution level the data exists, nationally and completely.** IPEDS
    publishes `ap_credit` and `dual_credit` as flags on every institution —
    does this college grant credit for AP, and for dual enrolment. That is a
    real property of a real node this graph already has.
  * **At course level it does not.** Nothing in IPEDS or the Civil Rights
    Data Collection says WHICH course earns WHICH credit at WHICH college.
    CRDC's dual-enrolment and AP endpoints are demographic COUNTS keyed on a
    school, a race, a sex and a disability status — they answer "how many
    students", never "which course".

So the tiers can be joined by a claim about an institution and not by a claim
about a course, and those support different questions.

Everything here reads the Urban Institute's Education Data API, which
`docs/sources/education-data.md` already clears under ODC-By. No new source,
no new licence question.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

from etl.identity import USER_AGENT
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "articulation-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_articulation --record` "
               "against the Urban Institute Education Data API (ODC-By, "
               "cleared in education-data.md). Counts are a census of the "
               "year named, not a sample.")

API = "https://educationdata.urban.org/api/v1"
ENDPOINTS = f"{API}/api-endpoints/"
YEAR = 2022

#: The institution-level flags IPEDS publishes about credit it will grant.
#: Named rather than discovered, because the finding is about these four
#: specifically and a probe that reported whatever it happened to match would
#: change its own subject when the API adds a field.
CREDIT_FLAGS = ("ap_credit", "dual_credit", "credit_for_life",
                "military_training_credit")

#: What a course-level answer would have to name. Searched across every
#: endpoint's URL and description — if a national source carried this, it
#: would be the source and everything else here would be secondary.
COURSE_LEVEL_TERMS = ("articulat", "credit accept", "course equivalen",
                      "transfer credit", "credit by exam")

#: IPEDS uses negative codes for "not applicable" and "not reported". They are
#: not zeroes and folding them in would report a missing answer as a refusal.
MISSING = {-1: "not reported", -2: "not applicable", -3: "suppressed"}


class Unreachable(RuntimeError):
    """The API did not answer. Distinct from answering with no rows."""


def get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as refused:
        raise Unreachable(f"{url}: HTTP {refused.code}") from refused
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


def institution_flags(year: int = YEAR) -> dict:
    """What IPEDS says about credit each institution will grant.

    A CENSUS — `per_page` is set above the population and the returned count
    is checked against it, because "3,240 institutions grant AP credit" is
    only a national figure if every institution was asked.
    """
    body = get(f"{API}/college-university/ipeds/institutional-characteristics/"
               f"{year}/?per_page=10000")
    rows = body.get("results") or []
    total = body.get("count")
    if total is None:
        raise Unreachable("the API answered without a count; a partial page "
                          "would understate every flag below")
    if len(rows) != total:
        raise Unreachable(
            f"the API reports {total} institutions and returned {len(rows)}. "
            f"Every figure here is a count over all of them.")

    flags = {}
    for flag in CREDIT_FLAGS:
        counted = collections.Counter(row.get(flag) for row in rows)
        answered = {value: n for value, n in counted.items()
                    if value in (0, 1)}
        missing = {MISSING.get(value, str(value)): n
                   for value, n in counted.items() if value not in (0, 1)}
        grants = answered.get(1, 0)
        asked = sum(answered.values())
        flags[flag] = {
            "grants": grants,
            "does_not": answered.get(0, 0),
            "answered": asked,
            "missing": missing,
            # Of the institutions that ANSWERED. Dividing by the population
            # would report a missing answer as a refusal.
            "percent_of_answered": round(100 * grants / asked, 1) if asked else None,
        }
    return {"year": year, "institutions": total, "flags": flags}


def course_level_sources(endpoints: list[dict]) -> dict:
    """Whether any endpoint claims to answer at COURSE level.

    The distinction the issue turns on. An endpoint counting students in dual
    enrolment answers "how many"; an edge needs "which course, which college,
    how many credits".
    """
    matched = []
    for endpoint in endpoints:
        blob = (f"{endpoint.get('endpoint_url', '')} "
                f"{endpoint.get('description', '')}").lower()
        for term in COURSE_LEVEL_TERMS:
            if term in blob:
                matched.append({"term": term,
                                "endpoint": endpoint.get("endpoint_url"),
                                "description": (endpoint.get("description")
                                                or "")[:160]})
                break
    return {"searched": len(endpoints), "terms": list(COURSE_LEVEL_TERMS),
            "matched": matched}


def crdc_granularity(year: int = 2017) -> dict:
    """What the dual-enrolment and AP endpoints are keyed on.

    Read from a row rather than described: the claim is that these answer
    "how many students" and not "which course", and the field names are the
    evidence.
    """
    found = {}
    for name, path in (
            ("dual_enrollment", f"schools/crdc/dual-enrollment/{year}/race/sex/"),
            ("ap_ib_enrollment", f"schools/crdc/ap-ib-enrollment/{year}/race/sex/"),
            ("offerings", f"schools/crdc/offerings/{year}/")):
        body = get(f"{API}/{path}?per_page=1")
        rows = body.get("results") or []
        fields = sorted(rows[0]) if rows else []
        found[name] = {
            "rows": body.get("count"),
            "fields": fields,
            # The question each answers, decided by what it is keyed on.
            "keyed_on": [f for f in fields
                         if f in ("ncessch", "leaid", "crdc_id", "race", "sex",
                                  "disability", "lep", "year", "fips")],
            "names_a_course": [f for f in fields if "course" in f],
            "names_an_institution": [f for f in fields
                                     if f in ("unitid", "opeid", "inst_name")],
            "names_a_credit_amount": [f for f in fields if "credit" in f],
        }
    return found


def measure(year: int = YEAR) -> dict:
    endpoints = (get(ENDPOINTS).get("results") or [])
    if not endpoints:
        raise Unreachable("the API listed no endpoints, so the course-level "
                          "search below would find nothing by not looking")
    return {
        "_": RECORD_NOTE,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%d"),
        "api": API,
        "institution_level": institution_flags(year),
        "course_level": course_level_sources(endpoints),
        "crdc": crdc_granularity(),
    }


def report(measured: dict) -> None:
    inst = measured["institution_level"]
    print(f"  IPEDS {inst['year']}, {inst['institutions']:,} institutions\n")
    for flag, found in inst["flags"].items():
        print(f"  {flag:<26} {found['grants']:>5,} grant / "
              f"{found['does_not']:>5,} do not   "
              f"{found['percent_of_answered']}% of those answering")
    course = measured["course_level"]
    print(f"\n  course-level sources among {course['searched']} endpoints: "
          f"{len(course['matched'])}")
    for hit in course["matched"]:
        print(f"    [{hit['term']}] {hit['endpoint']}")

    print("\n  what the CRDC endpoints are keyed on:")
    for name, found in measured["crdc"].items():
        print(f"    {name:<18} {found['rows']:>10,} rows  "
              f"course={found['names_a_course'] or '—'}  "
              f"institution={found['names_an_institution'] or '—'}  "
              f"credit={found['names_a_credit_amount'] or '—'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_articulation")
    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.json and args.record:
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2

    try:
        measured = measure(args.year)
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0
    report(measured)
    if args.record:
        if not measured["institution_level"]["institutions"]:
            print("refusing to --record a measurement of no institutions.",
                  file=sys.stderr)
            return 3
        write_record(RECORD, measured)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
