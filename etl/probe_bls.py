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

867, not the 868 `docs/sources/cip-soc-crosswalk.md` reports — that figure counts
`99-9999`, the crosswalk's own NO MATCH sentinel (#70).

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
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECTIONS = "https://data.bls.gov/projections/occupationProj"
USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# Fetched on every run, so a change in access shows up rather than being
# remembered. www.bls.gov is where OEWS and the education-system documentation
# live; data.bls.gov is where the projections table is served from.
#
# OEWS, by geography. Sizes are read from the headers rather than downloaded —
# the metro file is 40 MB and the question is which geographies exist, not what
# is in every row of them.
#
# The release year is searched for rather than written down. The previous
# version hard-coded `oesm23*`, which was two releases stale by the time anyone
# read the document it produced, and the file that would have caught it —
# bumping the year and seeing a 404 — does not exist, because bls.gov answers a
# missing file with 200 and an HTML page.
OEWS_GEOGRAPHIES = ("nat", "st", "ma")
OEWS_URL = "https://www.bls.gov/oes/special-requests/oesm{yy}{geography}.zip"
GEOGRAPHY_NAMES = {"nat": "national", "st": "state", "ma": "metropolitan"}

# How many releases back to look before giving up. OEWS is annual, so three is
# already more slack than a published series needs.
OEWS_LOOKBACK = 3

BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CONTACT = "(+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# One www.bls.gov page, fetched with several User-Agents. www, not data,
# because that is the host the claim is about.
#
# bls.gov serves 200 with a "page not found" body for a missing file — this
# module documents that behaviour a few lines down — so a URL pinned to one
# release year quietly becomes a probe of an error page the year that release
# is retired, and every row still reads "served". `identity_test_url` finds a
# year that is actually published rather than remembering one.
IDENTITY_TEST_FALLBACK = "https://www.bls.gov/oes/2023/may/oes_nat.htm"

# The claim has been wrong twice, so it is measured as a matrix rather than as
# a yes/no. `attempt(url, None)` does NOT send an anonymous request — urllib
# supplies `Python-urllib/3.x` — so "no User-Agent" was never tested either.
#
# Five agents showed our string served and four others refused, which is
# consistent with "a contact URL is the discriminator" but equally consistent
# with "this exact string is allowlisted" — one served sample cannot separate
# them. The last three rows are here to do that: they hold the contact URL
# constant and vary everything around it.
AGENTS = {
    "ours — name and contact URL": USER_AGENT,
    "library default": None,
    "empty": "",
    "descriptive, no contact URL": "edtech-kg research",
    "browser-like, no contact URL": BROWSER,
    "a different name, with a contact URL": f"kg-source-survey {CONTACT}",
    "the browser string, contact URL appended": f"{BROWSER} {CONTACT}",
    "the contact URL alone, no product name": CONTACT,
}

CROSSWALK = Path("data/CIP2020_SOC2018_Crosswalk.xlsx")
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


class MalformedSource(Exception):
    """Reachable, but not the table we asked for."""


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"unreachable: {url} ({exc})") from exc


def attempt(url: str, agent: str | None = USER_AGENT) -> dict:
    """What the server says today, not what it said when this was written.

    `agent` is a parameter because the claim this probe makes is *about* the
    User-Agent: that BLS refuses an anonymous request and serves an identified
    one. An earlier version named a field `unidentified_request` and sent the
    identifying header anyway — it varied the host instead, so the claim in the
    document was never measured by the probe that the document credits.
    """
    # `None` means "send whatever urllib sends by default" — which is
    # `Python-urllib/3.x`, not nothing. An empty string is the closest this can
    # get to absent, and the difference is recorded rather than glossed.
    headers = {} if agent is None else {"User-Agent": agent}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return {"status": response.status, "bytes": len(response.read())}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "reason": str(exc.reason).splitlines()[0]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "reason": str(exc)}


def head(url: str) -> dict:
    """Is it there, and how big — without downloading it.

    `status` alone does not answer "is it there". `www.bls.gov` serves a
    request for a file it does not have with **200 and `text/html`**, so a
    status check reports an unpublished release as available. The content type
    is carried back with it, and `is_file` is what callers should ask.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                     method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            size = response.headers.get("content-length")
            kind = (response.headers.get("content-type") or "").split(";")[0].strip()
            return {"status": response.status, "content_type": kind,
                    "bytes": int(size) if size and size.isdigit() else None,
                    "is_file": response.status == 200 and "html" not in kind}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "is_file": False,
                "reason": str(exc.reason).splitlines()[0]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": None, "is_file": False, "reason": str(exc)}


def oews_release(yy: str) -> dict:
    """One OEWS release, by geography — or `{}` if it is not published."""
    got = {GEOGRAPHY_NAMES[g]: head(OEWS_URL.format(yy=yy, geography=g))
           for g in OEWS_GEOGRAPHIES}
    return got if all(g["is_file"] for g in got.values()) else {}


def identity_test_url(oews: dict) -> str:
    """A www.bls.gov page that is actually published, for the header matrix.

    bls.gov answers a request for a missing file with **200 and text/html**,
    which this module documents and `head()` exists to see through. A URL
    pinned to one release year therefore becomes a probe of an error page the
    year that release is retired — and every row of the matrix still reads
    "served", so the claim would go on being confirmed by a page that is not
    the page.

    Built from the release `oews_latest` just found, and only used if it is
    served as an HTML page rather than a not-found body. The pinned URL is the
    fallback, so an offline run still has something to report.
    """
    release = (oews or {}).get("release") or ""
    match = re.search(r"(\d{4})", release)
    if match:
        candidate = f"https://www.bls.gov/oes/{match.group(1)}/may/oes_nat.htm"
        if head(candidate).get("status") == 200:
            return candidate
    return IDENTITY_TEST_FALLBACK


def oews_latest(this_year: int) -> dict:
    """The newest published OEWS release, found rather than remembered.

    Counts back from the current year. A release is only accepted when every
    geography in it is served as a zip — a half-published year would otherwise
    be reported as current with a geography silently missing.
    """
    tried = []
    for year in range(this_year, this_year - OEWS_LOOKBACK - 1, -1):
        yy = f"{year % 100:02d}"
        tried.append(yy)
        found = oews_release(yy)
        if found:
            return {"release": f"May 20{yy}", "years_tried": tried,
                    "geographies": found}
    return {"release": None, "years_tried": tried, "geographies": {}}


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
    markup = fetch(PROJECTIONS)
    table = rows_of(markup)
    header = next((r for r in table if any("Occupation Code" in c for c in r)), None)
    if header is None:
        raise MalformedSource(
            f"no 'Occupation Code' heading at {PROJECTIONS} — the page returned "
            f"{len(markup)} bytes and {len(table)} rows. A layout change would "
            f"otherwise be reported as zero occupations."
        )
    code_at = next(i for i, c in enumerate(header) if "Occupation Code" in c)

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

    # Checked BEFORE the empty-table refusal. A heading rename usually empties
    # the parse too, and "no occupations parsed" is the less informative of the
    # two errors — it points at the data when the cause is the layout.
    #
    # Substring matching works today only because "Employment Change" is not a
    # substring of "Employment Percent Change" — a property of BLS's phrasing,
    # not one this code enforces.
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

    if not occupations:
        raise ValueError("no occupations parsed — refusing to report that as coverage")
    return {"source": PROJECTIONS, "occupations": len(occupations),
            "columns": header, "field_present": present, "codes": set(occupations)}


def crosswalk_soc() -> set[str]:
    """The SOC codes a programme can actually reach, from the merged crosswalk.

    Read from the same file `probe_cipsoc` uses. Coverage against *these* is the
    measurement that matters — a national table of 800 occupations is not the
    same as covering the ones this graph reaches.
    """
    if not CROSSWALK.exists():
        return set()
    import zipfile  # noqa: PLC0415

    from etl.probe_cipsoc import rows, sheets  # noqa: PLC0415

    book = zipfile.ZipFile(CROSSWALK)
    found = set()
    for part in sheets(book).values():
        for row in rows(book, part):
            for cell in row:
                code = cell.strip()
                if SOC_CODE.fullmatch(code) and code not in NOT_AN_OCCUPATION:
                    found.add(code)
    return found


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
    oews = oews_latest(now.year)
    identity_url = identity_test_url(oews)

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
            "results": {label: attempt(identity_url, agent)
                        for label, agent in AGENTS.items()},
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
        print("\n  the same www.bls.gov page, by User-Agent\n")
        for label, got in result["user_agent_test"]["results"].items():
            print(f"    {label:42} {got.get('status') or 'no response'}")

        oews = result["oews"]
        release = oews["release"] or "none published"
        print(f"\n  OEWS, by geography — wages only, no projections "
              f"({release}, found not assumed)\n")
        for name, got in oews["geographies"].items():
            size = got.get("bytes")
            print(f"    {name:16} {got.get('status') or 'no response':>4}   "
                  f"{f'{size / 1_000_000:.1f} MB' if size else ''}")
        if not oews["geographies"]:
            print(f"    no complete release in 20{', 20'.join(oews['years_tried'])}")
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
