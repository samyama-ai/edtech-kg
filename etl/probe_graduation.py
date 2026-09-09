"""Are state graduation requirements obtainable? Robots first, then the data.

    python -m etl.probe_graduation --record

edtech-kg#41. A student choosing next semester solves two constraints:
prerequisites (what am I allowed to take) and graduation requirements (what
must I have by the end). Without the second, a plan can be prerequisite-valid
and still fail to graduate the student — **a wrong answer given confidently,
which is worse than no answer.**

The issue names the Education Commission of the States' 50-state comparison,
normalised to credits by subject, and is explicit about the licence:
*"ECS is a non-profit and this is their compilation — permission, not public
domain."*

**Permission is refused, and it is refused in the one place a machine is
expected to look.** `reports.ecs.org/robots.txt` is `Disallow: /`. The
compilation is there, it is exactly the shape the issue describes, and we may
not take it.

**Every fetch here is gated on robots.txt, checked first.** That is not
decoration: while exploring this issue I fetched the ECS table several times
BEFORE reading its robots.txt, which is the wrong order and is why the gate
is code rather than a habit. A probe that asks permission after the fact has
not asked.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from etl.identity import USER_AGENT
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "graduation-requirements-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_graduation --record`. Every "
               "fetch is gated on robots.txt, checked before the first "
               "request to a host. A source recorded as `refused` was never "
               "fetched.")

DELAY = 1.0

#: The sources the issue names, and the one alternative it asks about —
#: "whether going to the state regulations directly is cleaner, since the
#: underlying statutes are public even where the compilation is not."
SOURCES = {
    "ECS 50-state comparison": {
        "url": "https://reports.ecs.org/comparisons/"
               "high-school-graduation-requirements-01",
        "what": "the compilation the issue names — credits by subject, "
                "normalised across states",
        "is_the_compilation": True,
    },
    "ECS landing page": {
        "url": "https://www.ecs.org/"
               "50-state-comparison-high-school-graduation-requirements/",
        "what": "where the comparison is published for a reader",
    },
    "NCES state education reforms": {
        "url": "https://nces.ed.gov/programs/statereform/tab5_1.asp",
        "what": "the federal collection of state policy tables. This one is "
                "COMPULSORY ATTENDANCE AGE, not graduation requirements — "
                "the collection publishes no graduation-credit table, and "
                "this page is here for what its SOURCE line says rather than "
                "for its figures",
    },
}

#: Who a page credits its data to. NCES's state-policy tables cite the
#: Education Commission of the States, which is the same compilation the
#: first source refuses us — so the federal route is not an independent one.
CITES = re.compile(r"SOURCE:\s*(.{0,120})", re.I | re.S)


class Unreachable(RuntimeError):
    """A host did not answer. Distinct from refusing us."""


def robots_for(url: str) -> dict:
    """What the host's robots.txt says about this URL, before anything asks.

    A `robots.txt` that cannot be fetched is treated as PERMITTING — that is
    the convention, and refusing on a 404 would report every host without one
    as forbidding us. A 403 on the robots file itself is recorded as its own
    case, because a host that will not show its rules has not granted
    anything either.
    """
    parts = urllib.parse.urlsplit(url)
    location = f"{parts.scheme}://{parts.netloc}/robots.txt"
    request = urllib.request.Request(location, headers={"User-Agent": USER_AGENT})
    time.sleep(DELAY)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as refused:
        # No published rules, or none we may read. Neither is a prohibition.
        return {"robots_url": location, "robots_status": refused.code,
                "allowed": True, "why": "no readable robots.txt; the "
                                        "convention is that absence permits"}
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{location}: {gone}") from gone

    rules = urllib.robotparser.RobotFileParser()
    rules.parse(body.splitlines())
    allowed = rules.can_fetch(USER_AGENT, url)
    return {
        "robots_url": location,
        "robots_status": status,
        "allowed": allowed,
        "blanket_disallow": any(
            line.strip().lower() == "disallow: /" for line in body.splitlines()),
        "crawl_delay": rules.crawl_delay(USER_AGENT),
        "why": "robots.txt permits this path" if allowed
               else "robots.txt disallows this path",
    }


def fetch(url: str) -> dict:
    """One page — **only if robots.txt allows it.**

    The gate is here rather than in the caller so it cannot be forgotten, and
    the refusal is returned as data because whether a source may be taken IS
    the finding this issue asks for.
    """
    permission = dict(robots_for(url))
    if not permission["allowed"]:
        return {**permission, "url": url, "status": None, "bytes": 0,
                "fetched": False}

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(permission.get("crawl_delay") or DELAY)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
            return {**permission, "url": url, "status": response.status,
                    "bytes": len(body), "fetched": True, "body": body}
    except urllib.error.HTTPError as refused:
        return {**permission, "url": url, "status": refused.code,
                "bytes": 0, "fetched": False}
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


#: A cell stating a requirement as a bare credit count — the only shape that
#: structures cleanly. "4" does; "4, incl. English I, II, III, IV" names
#: courses on top of a count; "4 units English or English as a second
#: language*" is prose with a footnote.
BARE_COUNT = re.compile(r"^\d+(\.\d+)?$")


def cells(row: str) -> list[str]:
    return [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cell))).strip()
            for cell in re.findall(r"<t[dh].*?</t[dh]>", row, re.S | re.I)]


def cites(body: str) -> list[str]:
    """Who this page says its data came from.

    A federal page republishing a private compilation is not an alternative
    to that compilation, and the licence question follows the data rather
    than the host.
    """
    return [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", found)))
            .strip()[:160]
            for found in CITES.findall(body)][:3]


def shape_of(page: dict) -> dict:
    """How a fetched page states its requirements — counted, not described.

    Answers the issue's second question: *how many states express
    requirements as credits-per-subject, versus named courses, versus
    competency-based pathways. Only the first is cleanly structurable, and
    the count matters.*
    """
    body = page.get("body") or ""
    tables = re.findall(r"<table.*?</table>", body, re.S | re.I)
    if not tables:
        return {"tables": 0, "rows": 0,
                "note": "no HTML table; the requirements are not published as "
                        "one on this page"}

    rows = re.findall(r"<tr.*?</tr>", tables[0], re.S | re.I)
    header = cells(rows[0]) if rows else []
    # **A ROW IS A DATA ROW ONLY IF IT HAS AS MANY CELLS AS THE HEADER.**
    # NCES puts its footnotes and its SOURCE line in the same table as
    # single-cell rows, and counting those gave 85 "states" — more than there
    # are. A count that exceeds 51 is the kind of wrong that should be
    # obvious, and it was only obvious because someone read it.
    data = [c for c in (cells(r) for r in rows[1:])
            if len(c) >= max(2, len(header) - 1) and c[0].strip()]

    # The subject columns — everything after state and diploma type.
    subject_columns = max(0, len(header) - 2)
    bare, named, prose = 0, 0, 0
    for row in data:
        for cell in row[2:]:
            if not cell or cell in {"-", "—", "N/A"}:
                continue
            if BARE_COUNT.match(cell):
                bare += 1
            elif re.search(r"\bincl\.|\bincluding\b", cell, re.I):
                named += 1
            else:
                prose += 1

    return {
        "tables": len(tables),
        "rows": len(data),
        "columns": header,
        "subject_columns": subject_columns,
        "distinct_states": len({row[0] for row in data if row}),
        "rows_that_are_not_data": len(rows) - 1 - len(data),
        # Rows, not states: a state with three diploma types has three.
        "diploma_rows_per_state": round(
            len(data) / max(1, len({row[0] for row in data if row})), 1),
        "cells_as_a_bare_credit_count": bare,
        "cells_naming_courses_as_well": named,
        "cells_in_prose": prose,
        "percent_cleanly_structurable": (
            round(100 * bare / (bare + named + prose), 1)
            if (bare + named + prose) else None),
    }


def measure() -> dict:
    sources = {}
    for name, source in SOURCES.items():
        page = fetch(source["url"])
        body = page.pop("body", None)
        sources[name] = {**source, **page}
        if body is not None:
            sources[name]["cites"] = cites(body)
            # **Shape is computed only for a page that IS the graduation
            # compilation.** The NCES page is compulsory-attendance age, and
            # reporting "97.6% structurable" from it would be a figure about
            # the wrong subject sitting in a document about graduation
            # requirements — the exact confusion this repo keeps finding.
            if source.get("is_the_compilation"):
                sources[name]["shape"] = shape_of({"body": body})
            else:
                sources[name]["shape"] = {
                    "not_analysed": "this page is not the graduation-"
                                    "requirements compilation; it is here "
                                    "for its SOURCE line"}
    return {
        "_": RECORD_NOTE,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%d"),
        "sources": sources,
    }


def report(measured: dict) -> None:
    for name, found in measured["sources"].items():
        gate = "ALLOWED" if found["allowed"] else "REFUSED by robots.txt"
        print(f"  {name}")
        print(f"    {gate}  ({found['robots_status']} on "
              f"{found['robots_url']})")
        if not found["fetched"]:
            # WHICH refusal. "robots said no" and "the page itself refused"
            # are different findings, and the first version printed the
            # robots reason for both — so an ECS landing page returning 403
            # read as though robots had permitted and we had simply not
            # bothered.
            if not found["allowed"]:
                print(f"    not fetched — {found['why']}")
            else:
                print(f"    permitted, but the page answered "
                      f"{found['status']}")
            continue
        print(f"    {found['status']}, {found['bytes']:,} bytes")
        shape = found.get("shape") or {}
        if shape.get("not_analysed"):
            print(f"    {shape['not_analysed']}")
        elif shape.get("rows"):
            print(f"    {shape['rows']} rows, {shape['distinct_states']} states, "
                  f"{shape['diploma_rows_per_state']} diploma rows each")
            print(f"    cells: {shape['cells_as_a_bare_credit_count']} bare "
                  f"counts, {shape['cells_naming_courses_as_well']} naming "
                  f"courses, {shape['cells_in_prose']} prose "
                  f"({shape['percent_cleanly_structurable']}% structurable)")
        else:
            print(f"    {shape.get('note', 'no table')}")
        for said in found.get("cites") or []:
            print(f"    SOURCE: {said[:100]}")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_graduation")
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
        if not measured["sources"]:
            print("refusing to --record a measurement of no sources.",
                  file=sys.stderr)
            return 3
        write_record(RECORD, measured)
        print(f"  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
