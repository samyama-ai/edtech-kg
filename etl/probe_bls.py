"""Probe BLS for pay, outlook and entry education — the #37 question.

Three questions in `docs/questions.md` rest on what an occupation pays and
whether it is growing: Q17, Q18 and Q85. They were marked answerable on the
strength of O\\*NET, whose terms are still unconfirmed (#14). BLS publishes the
same substance as a federal agency, public domain, with no third-party terms.

    python -m etl.probe_bls                # the tables
    python -m etl.probe_bls --json         # machine-readable, with timestamp

The measurement that decides the issue is **coverage against the crosswalk**:
**867** SOC codes are reachable from a programme, and a field BLS does not carry
for one of them is a question we cannot answer. A national table with 800 rows
is not the same as coverage of the occupations this graph can reach.

867 rather than 868: the crosswalk once counted `99-9999`, its own NO MATCH
sentinel, as an occupation. `etl/probe_cipsoc.py` excludes it too since #70, so
the two probes agree.

**What `www.bls.gov` serves on turns on a contact URL in the User-Agent.** Not
identification, and not automation: a full browser string is refused, and a bare
`(+https://…)` with no product name at all is served. Measured across eight
User-Agents against one page, including the two that isolate the variable — the
same browser string with a contact URL appended, and a different project name
with one. Florida still refuses our identified request (#40, #50), so that
finding stands, but the general lesson is narrower than "a 403 means the
publisher blocks automation".

**`www.bls.gov` answers a request for a file that does not exist with 200 and an
HTML page.** So the OEWS release is *found*, not hard-coded: each candidate year
is confirmed to be served as a zip before it counts. A status check alone
reports next year's release as already published.

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone

# The MODULE, not its names. `from … import head` binds by value, so a test
# that replaces `bls_access.head` leaves this module calling the original —
# and the stub silently does nothing. One binding, one thing to patch.
from etl import bls_access
# At module level, not inside `crosswalk_soc`. The local form was there to keep
# the import cost off a run that never reads the crosswalk — but it also made
# the handle unobservable to a test, and `probe_cipsoc` is imported by this
# package anyway.
from etl import probe_cipsoc
from etl.probe_cipsoc import MissingSource

PROJECTIONS = "https://data.bls.gov/projections/occupationProj"

SOC_CODE = re.compile(r"\b\d{2}-\d{4}\b")

# Sentinels, not occupations. `99-9999` is the crosswalk's explicit "NO MATCH"
# row — a CIP that maps to nothing — and `00-0000` is the BLS all-occupations
# total. Counting either inflates a denominator with something that cannot be
# an answer.
NOT_AN_OCCUPATION = {"99-9999", "00-0000"}

# The columns the issue asks about, by their heading in the published table.
#
# The two employment columns are matched by PATTERN, not by the literal years.
# BLS republishes this table on a rolling decade — the 2024-34 projections
# become 2025-35 — and a heading pinned to "Employment 2024" would turn the
# next release into a hard MalformedSource, reported as "BLS stopped
# publishing employment" when BLS had done nothing but publish again.
#
# The rest are literal because their headings do not carry a date. Ordinary
# strings are matched as substrings, patterns by search, and the label is what
# is reported either way.
WANTED = ["Employment Change", "Employment Percent Change",
          "Occupational Openings", "Median Annual Wage",
          "Education, Work Experience, and Training"]

# `Employment 2024`, `Employment 2034`, and whatever they become next release.
EMPLOYMENT_YEAR = re.compile(r"\bEmployment\s+(\d{4})\b")


def employment_columns(header: list[str]) -> list[str]:
    """The dated employment headings actually published, in column order.

    Found rather than remembered, so the rolling decade — 2024-34 becoming
    2025-35 — is a change in what this reports and not a hard failure.
    """
    return [name for name in header if EMPLOYMENT_YEAR.search(name)]


# ONE class, defined beside the reading it describes. This module had its own
# and `probe_cipsoc` needed the same one once `crosswalk_soc` moved there
# (#112), so the name is re-exported rather than duplicated — every `except
# probe_bls.MalformedSource` and every exit code keeps working.
MalformedSource = probe_cipsoc.MalformedSource


def text_of(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def rows_of(markup: str) -> list[list[str]]:
    """The published table. The tags are uppercase, which is easy to miss."""
    out = []
    for row in re.findall(r"<TR[^>]*>(.*?)</TR>", markup, re.S | re.I):
        cells = [text_of(c) for c in
                 re.findall(r"<T[HD][^>]*>(.*?)</T[HD]>", row, re.S | re.I)]
        if cells:
            out.append(cells)
    return out


def projections() -> dict:
    """One row per detailed occupation, with what BLS publishes about it."""
    markup = bls_access.fetch(PROJECTIONS)
    table = rows_of(markup)
    header = next((r for r in table if any("Occupation Code" in c for c in r)), None)
    if header is None:
        raise MalformedSource(
            f"no 'Occupation Code' heading at {PROJECTIONS} — the page returned "
            f"{len(markup)} bytes and {len(table)} rows. A layout change would "
            f"otherwise be reported as zero occupations."
        )
    code_at = next(i for i, c in enumerate(header) if "Occupation Code" in c)

    # Checked BEFORE the rows are walked, not after. A heading rename usually
    # empties the parse too, and the comment below already says this error is
    # the more informative of the two — but it was raised after ~800 rows had
    # been read and scored against columns that were not there. The refusal
    # belongs where the fault is detectable.
    unmatched = [w for w in WANTED if not any(w in name for name in header)]
    if not employment_columns(header):
        # By pattern, not by year: a heading pinned to "Employment 2024" makes
        # the next release a hard failure, reported as BLS having stopped
        # publishing employment when BLS had only published again.
        unmatched.append("a dated Employment column")
    if unmatched:
        raise MalformedSource(
            f"no column matches {unmatched} at {PROJECTIONS} — the headings are "
            f"{header}. Reporting these as zero would read as BLS having stopped "
            f"publishing them.")

    # The dated employment headings are read off the header rather than
    # written down, so next release's 2025-35 is reported as itself.
    fields = WANTED + employment_columns(header)

    # Which columns belong to which field, resolved ONCE. This was recomputed
    # for every field on every row — 7 scans of the header per row, ~800 rows —
    # and the answer cannot change inside the loop.
    columns_for = {field: [i for i, name in enumerate(header) if field in name]
                   for field in fields}

    occupations, present = {}, dict.fromkeys(fields, 0)
    for row in table:
        if row is header or len(row) <= code_at:
            continue
        code = row[code_at].strip()
        if not SOC_CODE.fullmatch(code) or code in NOT_AN_OCCUPATION:
            continue
        if code in occupations:
            # Counted once per occupation, not once per row. A repeated code —
            # or a second table sharing the heading — would otherwise push a
            # field's coverage above the occupation count and print over 100%.
            continue
        occupations[code] = row
        # Once per field, not once per matching column. Two published columns
        # both containing a field's name — a second "Median Annual Wage", say —
        # would otherwise count twice and push coverage over 100%.
        for field, columns in columns_for.items():
            if any(i < len(row) and row[i] not in ("", "-", "—") for i in columns):
                present[field] += 1

    # Substring matching works today only because "Employment Change" is not a
    # substring of "Employment Percent Change" — a property of BLS's phrasing,
    # not one this code enforces.
    if not occupations:
        raise ValueError("no occupations parsed — refusing to report that as coverage")
    return {"source": PROJECTIONS, "occupations": len(occupations),
            "columns": header, "field_present": present, "codes": set(occupations)}


def crosswalk_soc() -> set[str]:
    """The SOC codes a programme can actually reach, from the merged crosswalk.

    ONE reading now, in `etl/probe_cipsoc.py` beside the workbook it reads —
    this module and `probe_codesets` each had their own, taking different
    routes to the same 867 codes (#112). Kept as a name here because the
    coverage figures below are the reason it exists.
    """
    return probe_cipsoc.soc_codes()


def probe(quiet: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    data = projections()
    reachable = crosswalk_soc()
    covered = data["codes"] & reachable if reachable else set()
    missing = reachable - data["codes"]

    # A missing code is not one fact. BLS does not project military
    # occupations at all; it publishes some others only at the broad level,
    # where the answer exists at coarser granularity; and the rest are simply
    # absent. Reporting one number for three different situations would make a
    # structural exclusion look like a data gap.
    military = {c for c in missing if c.startswith("55")}
    rolled_up = {c for c in missing - military if c[:-1] + "0" in data["codes"]}
    absent = missing - military - rolled_up

    # Sorted once. It was re-sorted for the JSON field and then twice more per
    # line of the printed block below.
    absent_sorted = sorted(absent)
    oews = bls_access.oews_latest(now.year)
    identity_url, identity_verified = bls_access.identity_test_url(oews)

    result = {
        "retrieved_at": stamp,
        "source": data["source"],
        "occupations": data["occupations"],
        "field_present": data["field_present"],
        "crosswalk_soc_codes": len(reachable),
        "crosswalk_codes_covered": len(covered),
        "crosswalk_codes_missing": len(missing),
        "missing_military": len(military),
        "missing_but_broad_parent_carried": len(rolled_up),
        "missing_outright": absent_sorted,
        "answerable_including_broad_parent": len(covered) + len(rolled_up),
        "oews": oews,
        # The same URL, several headers. That is the whole claim, so it is the
        # whole measurement.
        "user_agent_test": {
            "url": identity_url,
            # Whether the page was confirmed to BE the OEWS page, rather than
            # a 200 that is not it. Every row below reads "served" either way,
            # so this is the only thing separating the finding from an artefact.
            "url_verified": identity_verified,
            "results": {label: bls_access.attempt(identity_url, agent)
                        for label, agent in bls_access.AGENTS.items()},
        },
        "soc_vintage": "SOC 2018 — the crosswalk file is CIP2020_SOC2018",
    }

    if not quiet:
        print(f"\nBLS occupational projections — {data['source']}\n")
        print(f"  detailed occupations   {data['occupations']:>6,}")
        print("\n  field coverage, of those occupations\n")
        for name, count in data["field_present"].items():
            share = 100 * count / data["occupations"]
            print(f"    {name[:44]:44} {count:>5,}  {share:>5.1f}%")
        if reachable:
            share = 100 * len(covered) / len(reachable)
            print(f"\n  reachable from a programme (crosswalk) {len(reachable):>5,}")
            print(f"  of those, carried by BLS               {len(covered):>5,}"
                  f"  {share:.1f}%")
            print(f"\n  the {len(missing)} not carried are three different facts\n")
            print(f"    military occupations, never projected  {len(military):>5,}")
            print(f"    carried only at the broad level        {len(rolled_up):>5,}"
                  f"   answerable, coarser")
            print(f"    absent outright                        {len(absent):>5,}")
            effective = 100 * (len(covered) + len(rolled_up)) / len(reachable)
            print(f"\n  answerable one way or the other        "
                  f"{len(covered) + len(rolled_up):>5,}  {effective:.1f}%")
            # Named, not counted. These are the occupations the graph reaches
            # and cannot answer for, and a reader of the terminal output should
            # not have to re-run with --json to see which ones.
            if absent:
                print("\n  absent outright, in full\n")
                for line in range(0, len(absent_sorted), 8):
                    print("    " + "  ".join(absent_sorted[line:line + 8]))
        else:
            print("\n  crosswalk not present locally — run "
                  "`python -m etl.probe_cipsoc --download` for the coverage figure")
        matrix = result["user_agent_test"]
        print("\n  the same www.bls.gov page, by User-Agent")
        if not matrix["url_verified"]:
            # Every row below says "served" whether or not the URL is the page.
            # Unflagged, a soft 404 turns the whole finding into an artefact.
            print(f"    ⚠ {matrix['url']} could NOT be confirmed as the OEWS "
                  f"page — the rows below may all be describing an error body")
        print()
        for label, got in matrix["results"].items():
            print(f"    {label:42} {got.get('status') or 'no response'}")

        # Read from `result`, not rebound over the local of the same name that
        # produced it. Two bindings for one value in one function is how they
        # come to differ.
        release = oews["release"] or "none published"
        print(f"\n  OEWS, by geography — wages only, no projections "
              f"({release}, found not assumed)\n")
        for name, got in oews["geographies"].items():
            size = got.get("bytes")
            print(f"    {name:16} {got.get('status') or 'no response':>4}   "
                  f"{f'{size / 1_000_000:.1f} MB' if size else ''}")
        if not oews["geographies"]:
            # `'20' + yy` assumed every entry is a two-digit STRING. Four-digit
            # years or ints — either a plausible change in `bls_access` — would
            # print "202024" or crash on join. The years are normalised here
            # instead of trusting their shape.
            tried = ", ".join(f"20{y}" if len(str(y)) == 2 else str(y)
                              for y in oews["years_tried"])
            print(f"    no complete release in {tried or 'any year tried'}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_bls\n")

    return result


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json)
    except MissingSource as exc:
        # A MESSAGE, not a traceback, and not a zero. This is the case a fresh
        # clone hits first, and the fix is one command — so say which.
        print(f"\nsource missing: {exc}", file=sys.stderr)
        return 4
    except ValueError as exc:
        print(f"\nrefused: {exc}", file=sys.stderr)
        return 1
    except MalformedSource as exc:
        print(f"\nsource malformed: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"\nsource unreachable: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
