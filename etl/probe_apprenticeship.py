"""Probe the route to an occupation that is not a degree.

Two issues, one question. **edtech-kg#39** asks whether Registered
Apprenticeship is reachable as data, and how much of the occupational world it
covers that a CIP programme does not. **edtech-kg#38** asks whether
CareerOneStop can answer the licensure question `docs/questions.md` marks
unanswerable.

    python -m etl.probe_apprenticeship            # the tables
    python -m etl.probe_apprenticeship --json     # machine-readable
    python -m etl.probe_apprenticeship --reach    # re-check what answers

The number this exists to produce is the OVERLAP: how many occupations are
reachable by apprenticeship, how many by a programme, and how many by
apprenticeship **only**. That last set is what this graph cannot currently see,
and a course-planning product that cannot see it steers every student toward
tuition.

**No third-party dependency**, and no second workbook reader: `probe_cipsoc`
already has one that places cells by their `r` attribute, which is what stops a
row with a blank cell shifting every column after it.
"""

from __future__ import annotations

import argparse
import io
import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from etl import probe_cipsoc as crosswalk
from etl.probe_cipsoc import rows, sheets

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# O*NET publishes both sides of this question as crosswalks. That matters more
# than it sounds: the DOL routes edtech-kg#39 names — apprenticeship.gov's
# occupations page and the RAPIDS datasets on data.gov — do not answer, and are
# recorded below. These do.
RAPIDS_URL = ("https://www.onetcenter.org/crosswalks/rapids/"
              "Apprenticeship_RAPIDS_to_ONET-SOC.xlsx")
CIP_URL = ("https://www.onetcenter.org/crosswalks/cip/"
           "Education_CIP_to_ONET_SOC.xlsx")
RAPIDS_LOCAL = DATA_DIR / "Apprenticeship_RAPIDS_to_ONET-SOC.xlsx"
CIP_LOCAL = DATA_DIR / "Education_CIP_to_ONET_SOC.xlsx"

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# The crosswalk's own NO MATCH sentinel, excluded for the reason edtech-kg#70
# established: it is not an occupation.
NO_MATCH = "99-9999"

# What edtech-kg#38 asks about, and what this probe can say about it. Each is
# attempted rather than remembered — a source recorded as blocked on a date is
# a claim that goes stale, and the whole argument of these pages is that a
# figure comes from a run.
REACH = [
    ("careeronestop.org (web)", "https://www.careeronestop.org/"),
    ("careeronestop API", "https://api.careeronestop.org/v1/license/"),
    ("apprenticeship.gov (web)", "https://www.apprenticeship.gov/"),
    ("apprenticeship.gov API", "https://api.apprenticeship.gov/"),
    ("data.gov catalogue API", "https://catalog.data.gov/api/3/action/package_list"),
    ("O*NET RAPIDS crosswalk", RAPIDS_URL),
]


class MalformedSource(Exception):
    """A source that answered, but not with what it publishes."""


def download(url: str, into: Path) -> bytes:
    """Cached on disk. `data/` is gitignored, so this is a local cache and
    never a committed artefact."""
    if into.exists():
        return into.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise MalformedSource(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc
    if not payload.startswith(b"PK"):
        raise MalformedSource(
            f"{url} did not return a workbook — got {payload[:40]!r}")
    into.parent.mkdir(parents=True, exist_ok=True)
    into.write_bytes(payload)
    return payload


def crossings(url: str, into: Path) -> list[tuple[str, str]]:
    """(source code, O*NET-SOC code) from an O*NET crosswalk workbook.

    Both files share a layout — two title rows, then a header naming the
    O*NET-SOC column — so one reader serves both. The O*NET-SOC column is found
    by NAME rather than by position: these files carry four columns today and
    reading the third by index would keep working, wrongly, if a fifth arrived.
    """
    with zipfile.ZipFile(io.BytesIO(download(url, into))) as book:
        parts = sheets(book)
        if len(parts) != 1:
            raise MalformedSource(
                f"{into.name} holds {sorted(parts)} — refusing to guess which "
                f"sheet carries the mapping")
        table = rows(book, next(iter(parts.values())))

    head = next((i for i, r in enumerate(table)
                 if any("O*NET-SOC" in c and "Code" in c for c in r)), None)
    if head is None:
        raise MalformedSource(f"no header row in {into.name}")
    onet = next(i for i, c in enumerate(table[head])
                if "O*NET-SOC" in c and "Code" in c)

    out = [(r[0].strip(), r[onet].strip()) for r in table[head + 1:]
           if len(r) > onet and r[0].strip() and r[onet].strip()]
    if not out:
        raise MalformedSource(f"{into.name} parsed to zero rows")
    return out


def soc_of(onet_code: str) -> str:
    """`11-1011.03` -> `11-1011`.

    Every O*NET-SOC code carries a `.NN` suffix, so string equality against a
    SOC code matches NOTHING — measured on the occupation listing in
    edtech-kg#36 and confirmed here on a second, independent file. That is the
    safe failure; a partial match would be the dangerous one. The rollup is
    the join, and it has to be written down rather than assumed.
    """
    return onet_code.split(".")[0]


def our_soc() -> set[str]:
    """The SOC codes the CIP-SOC crosswalk this repo already loads can reach."""
    if not crosswalk.LOCAL.exists():
        try:
            crosswalk.download()
        except (RuntimeError, ValueError) as exc:
            raise MalformedSource(
                f"could not fetch the CIP-SOC crosswalk: {exc}") from exc
    with zipfile.ZipFile(crosswalk.LOCAL) as book:
        table = rows(book, sheets(book)["CIP-SOC"])
    mapped, _ = crosswalk.pairs(table, crosswalk.find_header(table, "CIP"))
    return {soc for _, soc in mapped if soc != NO_MATCH}


def routes() -> dict:
    """The two ways into an occupation, and what only one of them reaches."""
    apprentice = crossings(RAPIDS_URL, RAPIDS_LOCAL)
    programme = crossings(CIP_URL, CIP_LOCAL)

    a_onet = {onet for _, onet in apprentice}
    p_onet = {onet for _, onet in programme}
    a_soc = {soc_of(o) for o in a_onet}
    p_soc = {soc_of(o) for o in p_onet}
    ours = our_soc()

    return {
        "rapids_rows": len(apprentice),
        "rapids_codes": len({code for code, _ in apprentice}),
        "apprentice_onet": len(a_onet),
        "apprentice_soc": len(a_soc),
        "programme_rows": len(programme),
        "programme_onet": len(p_onet),
        "programme_soc": len(p_soc),
        "both_ways": len(a_soc & p_soc),
        # The finding. These occupations have a public, funded route into them
        # that this graph has no shape for.
        "apprenticeship_only": sorted(a_soc - p_soc),
        "programme_only": len(p_soc - a_soc),
        "our_crosswalk_soc": len(ours),
        "apprenticeable_in_ours": len(a_soc & ours),
        "apprentice_soc_missing_from_ours": sorted(a_soc - ours),
        # Re-measured here rather than cited: every O*NET-SOC code carries a
        # suffix, so a naive join against SOC finds nothing at all.
        "naive_string_matches": len(a_onet & ours),
    }


def reachable() -> list[dict]:
    """What answers a request, and what does not — attempted, not remembered.

    DNS is resolved separately from the connection, because they fail
    differently and the difference is the whole finding. A host that resolves
    and refuses TCP is a source that will not talk to this network; a host
    whose name resolves NOWHERE is a broken chain at the publisher's end, and
    only the second can be asserted without qualification.
    """
    out = []
    for name, url in REACH:
        host = urllib.parse.urlparse(url).hostname or ""
        record = {"source": name, "url": url, "dns": None, "status": None}
        try:
            record["dns"] = socket.gethostbyname(host)
        except OSError as exc:
            record["status"] = f"name does not resolve ({exc.strerror or exc})"
            out.append(record)
            continue
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                         method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                record["status"] = str(response.status)
        except urllib.error.HTTPError as exc:
            record["status"] = str(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            record["status"] = f"no connection ({reason})"
        out.append(record)
    return out


def probe(quiet: bool = False, with_reach: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    found = routes()
    reach = reachable() if with_reach else []

    if not quiet:
        print("\nRegistered Apprenticeship — the route that is not a degree\n")
        print(f"  RAPIDS rows                      {found['rapids_rows']:>8,}")
        print(f"  distinct apprenticeship codes    {found['rapids_codes']:>8,}")
        print(f"  O*NET-SOC occupations reached    {found['apprentice_onet']:>8,}")
        print(f"  rolled up to SOC                 {found['apprentice_soc']:>8,}")

        print("\nAgainst the programme route\n")
        print(f"  SOC reachable by a CIP programme {found['programme_soc']:>8,}")
        print(f"  reachable BOTH ways              {found['both_ways']:>8,}")
        print(f"  reachable ONLY by apprenticeship {len(found['apprenticeship_only']):>8}"
              "   <- this graph has no shape for these")
        print(f"  reachable ONLY by a programme    {found['programme_only']:>8,}")

        print("\nJoining to the crosswalk this repo loads\n")
        print(f"  SOC our crosswalk carries        {found['our_crosswalk_soc']:>8,}")
        print(f"  of those, apprenticeable         {found['apprenticeable_in_ours']:>8,}")
        print(f"  apprenticeship SOC not in ours   "
              f"{len(found['apprentice_soc_missing_from_ours']):>8}")
        print(f"  naive O*NET-SOC = SOC matches    {found['naive_string_matches']:>8}"
              f"   of {found['apprentice_onet']:,}  <- the suffix")

        if with_reach:
            print("\nWhat answers a request\n")
            for row in reach:
                print(f"  {row['source']:<28} {row['status']}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_apprenticeship\n")

    return {"retrieved_at": stamp, "routes": found, "reachable": reach}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    parser.add_argument("--reach", action="store_true",
                        help="Re-check which sources answer a request. Off by "
                             "default because the blocked ones time out, which "
                             "makes a plain run slow for no new figure.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json, with_reach=args.reach or args.json)
    except MalformedSource as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
