"""The rules joining secondary to post-secondary: captured as flags, written as prose.

    python -m etl.probe_progression_rules --record

edtech-kg#66. Four blocked questions share one shape — every rule that would
answer them exists, is public, and is written for humans:

  Q39  which courses satisfy this programme's entry requirement?  admission rules
  Q57  a state changes graduation requirements — what becomes mandatory?  state policy
  Q58  an accreditation lapses — what is affected?  accreditor scope
  Q93  which pathways cross into post-secondary?  articulation agreements

The issue says this is the third time the shape has appeared, and asks whether
it holds. It does, and the measurement sharpens it: **the national data does
not omit these rules. It captures each one as a FLAG and drops the
substance.**

IPEDS knows that 6,000-odd institutions require "college preparatory courses".
It does not name one. That is the pattern in a sentence, and it is worse for a
graph than an absence would be — a flag looks loadable.

Q93 is not re-measured here. `docs/sources/articulation-measured.json` already
holds it, from edtech-kg#42, and measuring it twice would give this page a
second figure to drift against.
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
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "progression-rules-measured.json"
ARTICULATION = ROOT / "docs" / "sources" / "articulation-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_progression_rules --record`. "
               "Q93 is read from articulation-measured.json (edtech-kg#42) "
               "rather than re-measured, so the two pages cannot drift.")

API = "https://educationdata.urban.org/api/v1"
ADMISSIONS = f"{API}/college-university/ipeds/admissions-requirements/2022/"

#: Where each rule is published, and what this probe asks of it.
SOURCES = {
    "Q57 state graduation requirements": {
        "ecs": "https://www.ecs.org/50-state-comparison-high-school-graduation-requirements/",
        "nces": "https://nces.ed.gov/programs/statereform/tab1_1.asp",
    },
    "Q58 accreditor scope": {
        "dapip": "https://ope.ed.gov/dapip/#/download-data-files",
    },
}

#: A field that names a COURSE rather than flagging that courses are required.
#: The distinction the whole issue turns on: `reqt_college_prep` is a boolean
#: about coursework; a course-level rule would carry a title, a code or a
#: subject with a credit count.
#: Tokens that would mean a column names COURSEWORK rather than flagging it.
#:
#: **Compared as whole tokens, not as substrings.** An unbounded `unit`
#: matched `unitid` — the institution key — and the probe reported "1 field
#: names a course" for a column naming a college, which is this finding
#: inverted. A `\b` does not fix it either: `_` is a word character, so
#: `\bcourse\b` misses a real `course_credits`. Field names are split on
#: `_` and the tokens compared.
COURSE_TOKENS = {"course", "courses", "subject", "subjects", "credit",
                 "credits", "unit", "units", "title", "cip"}

#: Columns whose tokens match and which still do not name coursework.
#: `years_college_reqd` is a scalar count of years.
NOT_A_COURSE = {"years_college_reqd"}


class Unreachable(RuntimeError):
    """A host did not answer at all. Distinct from answering with a refusal."""


def fetch(url: str) -> tuple[int | str, str]:
    """Status and body — a refusal is a measurement, not an error."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as refused:
        return refused.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


def names_coursework(field: str) -> bool:
    """Does a column name coursework, or flag that coursework is required?

    The distinction the whole issue turns on. `reqt_college_prep` is a boolean
    ABOUT coursework; a course-level rule would carry a title, a code, a
    subject or a credit count.
    """
    if field in NOT_A_COURSE:
        return False
    return bool(set(re.split(r"[^a-z0-9]+", field.lower())) & COURSE_TOKENS)


def admission_rules() -> dict:
    """Q39 — does IPEDS name the courses a college requires, or flag them?

    A census: the returned rows are checked against the API's own count,
    because "6,138 institutions and not one named course" is a national claim
    only if every institution was asked.
    """
    status, body = fetch(f"{ADMISSIONS}?per_page=10000")
    if status != 200:
        raise Unreachable(f"IPEDS admissions answered {status}")
    payload = json.loads(body)
    rows = payload.get("results") or []
    total = payload.get("count")
    if total is None or len(rows) != total:
        raise Unreachable(
            f"the API reports {total} institutions and returned {len(rows)}; "
            f"a partial page would understate the flags below")

    fields = sorted(rows[0]) if rows else []
    flags = [f for f in fields if f.startswith("reqt_")]
    naming = [f for f in fields if names_coursework(f)]

    # How many institutions the coursework flags actually fire for. A flag
    # nobody sets would make "the substance is missing" true and uninteresting.
    coursework = {}
    for flag in ("reqt_college_prep", "reqt_competencies", "reqt_hs_record"):
        if flag in fields:
            coursework[flag] = sum(1 for r in rows if r.get(flag) == 1)

    return {
        "endpoint": ADMISSIONS,
        "institutions": total,
        "fields": len(fields),
        "requirement_flags": flags,
        "fields_naming_a_course": naming,
        "institutions_requiring_coursework": coursework,
    }


def published_as_prose() -> dict:
    """Q57 and Q58 — is the rule reachable as data, or as a page?

    Three things separate a dataset from a document, and all three are
    recorded: the status, whether the body parses as JSON, and whether the
    page links a downloadable file. A host answering 200 with an application
    shell has published nothing a machine can read.
    """
    found = {}
    for question, sources in SOURCES.items():
        found[question] = {}
        for name, url in sources.items():
            status, body = fetch(url)
            found[question][name] = {
                "url": url,
                "status": status,
                "bytes": len(body),
                "is_json": _is_json(body),
                "html_tables": len(re.findall(r"<table", body, re.I)),
                "downloadable_files": sorted(set(re.findall(
                    r'href="([^"]*\.(?:csv|xlsx?|zip|json))"', body, re.I)))[:5],
            }
    return found


def _is_json(body: str) -> bool:
    if not body.strip():
        return False
    try:
        json.loads(body)
        return True
    except json.JSONDecodeError:
        return False


def _shown(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def articulation_from_the_record() -> dict:
    """Q93, read from edtech-kg#42's record rather than re-measured.

    Two probes measuring one fact is two figures that can disagree, and this
    page would be quoting the other one's conclusion either way.
    """
    if not ARTICULATION.exists():
        return {"note": "articulation-measured.json is not committed; run "
                        "`python -m etl.probe_articulation --record` first",
                "available": False}
    found = json.loads(ARTICULATION.read_text(encoding="utf-8"))
    course = found["course_level"]
    return {
        "available": True,
        #  raises when a test repoints ARTICULATION outside
        # the repo. The path is for a reader either way.
        "source": _shown(ARTICULATION),
        "retrieved_at": found["retrieved_at"],
        "endpoints_searched": course["searched"],
        "endpoints_naming_a_course_level_rule": len(course["matched"]),
        "institution_level_flags": sorted(
            found["institution_level"]["flags"]),
    }


def measure() -> dict:
    return {
        "_": RECORD_NOTE,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%d"),
        "q39_admission_rules": admission_rules(),
        "published_as_prose": published_as_prose(),
        "q93_articulation": articulation_from_the_record(),
    }


def report(measured: dict) -> None:
    q39 = measured["q39_admission_rules"]
    print(f"  Q39  IPEDS admissions, {q39['institutions']:,} institutions, "
          f"{q39['fields']} fields")
    print(f"       {len(q39['requirement_flags'])} requirement flags, "
          f"{len(q39['fields_naming_a_course'])} naming a course")
    for flag, n in q39["institutions_requiring_coursework"].items():
        print(f"       {flag:<22} set for {n:,}")

    print()
    for question, sources in measured["published_as_prose"].items():
        print(f"  {question}")
        for name, found in sources.items():
            print(f"       {str(found['status']):<5} {name:<7} "
                  f"{found['bytes']:>7} bytes  json={found['is_json']}  "
                  f"tables={found['html_tables']}  "
                  f"files={len(found['downloadable_files'])}")

    q93 = measured["q93_articulation"]
    if q93.get("available"):
        print(f"\n  Q93  from {q93['source']} ({q93['retrieved_at']}): "
              f"{q93['endpoints_naming_a_course_level_rule']} of "
              f"{q93['endpoints_searched']} endpoints name a course-level rule")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_progression_rules")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.json and args.record:
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2

    try:
        measured = measure()
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0
    report(measured)
    if args.record:
        if not measured["q39_admission_rules"]["institutions"]:
            print("refusing to --record a measurement of no institutions.",
                  file=sys.stderr)
            return 3
        write_record(RECORD, measured)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
