"""Probe College Scorecard earnings — who they cover, and how often (#21).

`docs/scope.md` records one caveat: the figures cover federal-aid recipients
only. That was written from general knowledge and had not been checked. It is
correct, and it is **not the only caveat** — the published definition carries
two more, and one of them biases the number upward.

    python -m etl.probe_scorecard             # the tables
    python -m etl.probe_scorecard --json      # machine-readable, with timestamp
    python -m etl.probe_scorecard --download  # fetch the data file first

The measurement that matters is **how often a figure is actually there**. A
field that exists in 178 columns is not the same as a field with a value, and
most of these are privacy-suppressed rather than published.

**The download URL is date-stamped and changes every release**, so it is
discovered from the data page rather than hardcoded — a pinned link would 404
silently on the next publication.

No third-party dependency, as with the other probes.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DATA_PAGE = "https://collegescorecard.ed.gov/data/"
GLOSSARY = "https://collegescorecard.ed.gov/data/glossary/"
USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"
ARCHIVE = Path("data/scorecard-field-of-study.zip")

# The two markers this file uses where a value is not published. Guessing them
# is how a first pass reported 100% coverage: neither is blank, so anything
# testing for emptiness counts a suppression as a figure.
SUPPRESSED = "PS"          # too few students to publish without identifying them
NOT_APPLICABLE = "NA"

# Median earnings, by how long after completion. EARN_MDN_4YR is the one the
# glossary defines and the website shows.
HORIZONS = {
    "EARN_MDN_1YR": "1 year after completion",
    "EARN_MDN_HI_2YR": "2 years, high earners excluded",
    "EARN_NE_MDN_3YR": "3 years, not enrolled",
    "EARN_MDN_4YR": "4 years after completion — the published figure",
    "EARN_MDN_5YR": "5 years after completion",
}


class MalformedSource(Exception):
    """Reachable, but not what we asked for."""


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"unreachable: {url} ({exc})") from exc


def field_of_study_url() -> str:
    """Discovered, not hardcoded.

    The published link carries the release date — `..._06102026.zip` — so it
    changes every publication. A pinned URL would 404 on the next release and
    the probe would report a source problem where there is none.
    """
    page = fetch(DATA_PAGE).decode("utf-8", "replace")
    links = re.findall(r'href="([^"]+Field-of-Study[^"]*\.zip)"', page)
    if not links:
        raise MalformedSource(
            f"no Field-of-Study download link on {DATA_PAGE} — the page returned "
            f"{len(page)} bytes. A rename would otherwise look like missing data."
        )
    return links[0]


def download(path: Path | None = None) -> Path:
    # Resolved at call time, not bound at import. A default of `ARCHIVE`
    # is evaluated once when the module loads, so a test — or anything
    # else — pointing the probe elsewhere is silently ignored and the
    # real 17 MB file is used instead.
    path = path or ARCHIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fetch(field_of_study_url()))
    return path


def rows(path: Path | None = None):
    """One row per institution × programme × credential level."""
    path = path or ARCHIVE
    book = zipfile.ZipFile(path)
    name = next((n for n in book.namelist() if n.lower().endswith(".csv")), None)
    if name is None:
        raise MalformedSource(f"{path} contains no CSV: {book.namelist()}")
    with book.open(name) as handle:
        yield from csv.DictReader(
            io.TextIOWrapper(handle, encoding="utf-8-sig", errors="replace"))


def coverage(path: Path | None = None) -> dict:
    """How often an earnings figure is actually published."""
    path = path or ARCHIVE
    total = 0
    institutions, programmes = set(), set()
    labels: dict[str, str] = {}
    by_level = collections.Counter()
    published = collections.Counter()
    suppressed = collections.Counter()
    not_applicable = collections.Counter()
    level_published = collections.Counter()

    for row in rows(path):
        total += 1
        level = row.get("CREDLEV", "")
        # The file carries its own labels. Naming the levels here instead
        # produced a table saying Bachelor's had 1,249 rows, which is wrong and
        # looked plausible.
        labels.setdefault(level, (row.get("CREDDESC") or "").strip())
        by_level[level] += 1
        institutions.add(row.get("UNITID"))
        programmes.add((row.get("CIPCODE"), level))
        for field in HORIZONS:
            value = (row.get(field) or "").strip()
            if value.isdigit():
                published[field] += 1
                level_published[(field, level)] += 1
            elif value == SUPPRESSED:
                suppressed[field] += 1
            elif value == NOT_APPLICABLE:
                not_applicable[field] += 1

    if not total:
        raise ValueError("no rows read — refusing to report that as coverage")

    headline = "EARN_MDN_4YR"
    return {
        "rows": total,
        "institutions": len(institutions),
        "programmes": len(programmes),
        "horizons": {
            field: {
                "published": published[field],
                "suppressed": suppressed[field],
                "not_applicable": not_applicable[field],
                "share": round(100 * published[field] / total, 1),
            }
            for field in HORIZONS
        },
        "by_credential_level": {
            level: {
                "label": labels.get(level, ""),
                "rows": count,
                "published": level_published[(headline, level)],
                "share": round(100 * level_published[(headline, level)] / count, 1),
            }
            for level, count in sorted(by_level.items(), key=lambda kv: (len(kv[0]), kv[0]))
        },
    }


def cohort_definition() -> dict:
    """The published definition, read rather than remembered.

    `docs/scope.md` recorded one caveat from general knowledge. This is what the
    source actually says, so the wording that travels with an answer comes from
    the publisher.
    """
    page = fetch(GLOSSARY).decode("utf-8", "replace")
    text = " ".join(re.sub(r"<[^>]+>", " ", page).split())
    text = text.replace("&#8217;", "'").replace("&amp;", "&")
    start = text.find("Median Earnings")
    if start < 0:
        raise MalformedSource(f"no 'Median Earnings' entry in the glossary at {GLOSSARY}")
    quoted = text[start:start + 780]
    return {
        "source": GLOSSARY,
        "quoted": quoted,
        # Each is a filter on who is counted. The first is the one already
        # recorded; the other two are not, and the second raises the figure.
        "federal_aid_only": "received federal financial aid" in quoted,
        "working_and_not_enrolled": "not be enrolled" in quoted,
        "measured_at": "fourth full year" if "fourth full year" in quoted else None,
    }


def probe(path: Path | None = None, quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = path or ARCHIVE
    if not path.exists():
        raise ValueError(
            f"{path} not found. Run `python -m etl.probe_scorecard --download` "
            f"to fetch it — the file is ~17 MB and is not committed.")
    measured = coverage(path)
    cohort = cohort_definition()
    result = {"retrieved_at": stamp, "source": DATA_PAGE, "cohort": cohort, **measured}

    if not quiet:
        print("\nCollege Scorecard — field of study\n")
        print(f"  rows                {measured['rows']:>9,}"
              "   institution x programme x credential level")
        print(f"  institutions        {measured['institutions']:>9,}")
        print(f"  programme x level   {measured['programmes']:>9,}")

        print("\n  how often an earnings figure is published\n")
        for field, label in HORIZONS.items():
            got = measured["horizons"][field]
            print(f"    {field:18} {got['published']:>7,}  {got['share']:>5.1f}%"
                  f"   suppressed {got['suppressed']:>7,}   {label}")

        print("\n  by credential level, at four years\n")
        for level, got in measured["by_credential_level"].items():
            print(f"    {level:>3}  {got['label'][:34]:36} {got['published']:>6,}"
                  f"/{got['rows']:>7,}  {got['share']:>5.1f}%")

        print("\n  who is counted\n")
        print(f"    federal aid recipients only      {cohort['federal_aid_only']}")
        print(f"    and working, and not enrolled    {cohort['working_and_not_enrolled']}")
        print(f"    measured                         {cohort['measured_at']}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_scorecard\n")

    return result


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--download", action="store_true",
                        help="Fetch the field-of-study archive first.")
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)
    try:
        if args.download:
            download()
        result = probe(quiet=args.json)
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
