"""Probe the route to an occupation that is not a degree.

Two issues, one question. **edtech-kg#39** asks whether Registered
Apprenticeship is reachable as data, and how much of the occupational world it
covers that a CIP programme does not. **edtech-kg#38** asks whether
CareerOneStop can answer a licensure question it attributes to
`docs/questions.md` — that attribution does not hold, and
`docs/sources/careeronestop.md` records what the file actually says.

    python -m etl.probe_apprenticeship            # the tables
    python -m etl.probe_apprenticeship --json     # machine-readable
    python -m etl.probe_apprenticeship --reach    # re-check what answers

The number this exists to produce is the OVERLAP, measured against BOTH
CIP-to-SOC crosswalks because they disagree: against O*NET's the exclusive
set is 63, against the NCES file this repo loads it is 0. The 63 measures
how far two official crosswalks differ.

**No third-party dependency**, and no second workbook reader: `probe_cipsoc`
places cells by their `r` attribute, which stops a row with a blank cell
shifting every column after it.
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from etl import probe_cipsoc as crosswalk
from etl.probe_cipsoc import rows, sheets
# Whether a source answers lives next door; this module is the crosswalk
# arithmetic. `USER_AGENT` comes from there so both halves identify
# themselves the same way.
from etl.reach import USER_AGENT, reachable

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


# The crosswalk's own NO MATCH sentinel, excluded for the reason edtech-kg#70
# established: it is not an occupation.
NO_MATCH = "99-9999"


# Queried alongside the system resolver. The page's whole argument rests on
# telling "this network cannot resolve it" apart from "it resolves nowhere",
# and one `gethostbyname()` call cannot make that distinction.
#: An A or AAAA answer, as `dig +short` prints one. Anything else in that
#: output is a CNAME, a message, or part of a chain.
ADDRESS = re.compile(r"\A(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]{3,})\Z")

PUBLIC_RESOLVERS = (("Google", "8.8.8.8"), ("Cloudflare", "1.1.1.1"))


class MalformedSource(Exception):
    """A source that answered, but not with what it publishes."""


#: The two workbooks are under 2 MB. This guards a redirect to something else,
#: not a size prediction: an unbounded `read()` on a 180s timeout pulls
#: whatever it is pointed at into memory.
MAX_DOWNLOAD = 64 * 1024 * 1024


def download(url: str, into: Path) -> bytes:
    """Cached on disk — `data/` is gitignored, so never a committed artefact.

    The cache is CHECKED, not trusted on existence: a truncated write or an
    HTML error page under the workbook's name was served to every later run
    as the file, and the refusal that catches that only runs on download.
    """
    if into.exists():
        cached = into.read_bytes()
        if cached.startswith(b"PK") and len(cached) > 1024:
            return cached
        # Removed, or every run from here reads the same bad bytes.
        into.unlink()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = response.read(MAX_DOWNLOAD + 1)
        if len(payload) > MAX_DOWNLOAD:
            raise MalformedSource(
                f"{url} returned more than {MAX_DOWNLOAD // (1024 * 1024)} MB; "
                f"the workbooks are under 2 MB, so this is a redirect to "
                f"something else rather than a bigger file.")
    except urllib.error.HTTPError as exc:
        raise MalformedSource(f"{url} returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError,
            http.client.HTTPException) as exc:
        # `http.client.HTTPException` too. `IncompleteRead` derives from it
        # ALONE — not from OSError — so a truncated chunked response escaped
        # every handler here and came out as a traceback. onetcenter.org
        # serves chunked and has truncated in practice, so this is observed
        # rather than defensive: on pages arguing that failures arrive as a
        # stated `refused:`, a transient truncation read as a broken probe.
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
    # The SOURCE column by name too. It was `r[0]` while the O*NET column was
    # resolved by heading, so a file that gains a column on the left keeps
    # parsing and pairs the wrong two values.
    # ALL matches, then exactly one. `next(...)` took the first, so a workbook
    # that gained a "Match Code" column to the LEFT of the real source column
    # would pair the wrong values and keep parsing — the failure the comment
    # above claims to prevent, arriving through the fix for it.
    candidates = [i for i, c in enumerate(table[head])
                  if "Code" in c and "O*NET-SOC" not in c]
    if len(candidates) > 1:
        raise MalformedSource(
            f"{into.name} has {len(candidates)} candidate source columns "
            f"{[table[head][i] for i in candidates]}; this pairs one against "
            f"the O*NET column and cannot choose between them.")
    source = candidates[0] if candidates else None
    if source is None:
        raise MalformedSource(
            f"no source code column in {into.name}; its header is "
            f"{table[head]}. Pairing against column 0 is how a reordered file "
            f"keeps parsing and pairs the wrong values.")

    wide = max(source, onet)
    out = [(r[source].strip(), r[onet].strip()) for r in table[head + 1:]
           if len(r) > wide and r[source].strip() and r[onet].strip()]
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
        except (RuntimeError, ValueError, urllib.error.URLError,
                TimeoutError, OSError) as exc:
            # A network failure escaped as a traceback: the crosswalk
            # download raises URLError, and only RuntimeError and
            # ValueError were caught.
            raise MalformedSource(
                f"could not fetch the CIP-SOC crosswalk: {exc}") from exc
    with zipfile.ZipFile(crosswalk.LOCAL) as book:
        parts = sheets(book)
        if "CIP-SOC" not in parts:
            # A renamed sheet escaped as `KeyError: 'CIP-SOC'`, past `main`'s
            # handler and out as a traceback — in the one function whose
            # network failure was already wrapped for that reason.
            raise MalformedSource(
                f"the CIP-SOC workbook has no 'CIP-SOC' sheet; it holds "
                f"{sorted(parts)}. NCES has renamed or restructured it, and "
                f"every SOC code below is read from that sheet.")
        table = rows(book, parts["CIP-SOC"])
    mapped, _ = crosswalk.pairs(table, crosswalk.find_header(table, "CIP"))
    return {soc for _, soc in mapped if soc != NO_MATCH}


# SOC major groups, by the first two digits of the code. Only the groups the
# apprenticeship set actually reaches need names; anything else is reported by
# its number rather than guessed at.
SOC_GROUPS = {
    "11": "Management", "13": "Business and Financial",
    "15": "Computer and Mathematical", "17": "Architecture and Engineering",
    "19": "Life, Physical and Social Science", "21": "Community and Social Service",
    "23": "Legal", "25": "Education", "27": "Arts, Design and Media",
    "29": "Healthcare Practitioner", "31": "Healthcare Support",
    "33": "Protective Service", "35": "Food Preparation and Serving",
    "37": "Building and Grounds Cleaning", "39": "Personal Care",
    "41": "Sales", "43": "Office and Administrative Support",
    "45": "Farming, Fishing and Forestry", "47": "Construction and Extraction",
    "49": "Installation, Maintenance and Repair", "51": "Production",
    "53": "Transportation and Material Moving", "55": "Military",
}


def by_major_group(apprentice: set[str], programme: set[str]) -> list[dict]:
    """Where the apprenticeship-only occupations actually sit.

    The most useful half of this page's finding, and it was hand-typed:
    measured in a shell, written into the document, and published under a
    heading promising every figure came from the probe. It comes from the
    probe now.

    The point it makes is that the exclusive set is NOT the trades — so the
    per-group split has to be computed rather than asserted, or the claim
    rests on arithmetic nobody can re-run.
    """
    groups = sorted({soc[:2] for soc in apprentice})
    out = []
    for prefix in groups:
        mine = {s for s in apprentice if s.startswith(prefix)}
        shared = mine & programme
        out.append({
            "group": prefix,
            "name": SOC_GROUPS.get(prefix, f"SOC {prefix}"),
            "apprenticeable": len(mine),
            "also_via_a_programme": len(shared),
            "only_apprenticeship": len(mine - shared),
            # Printed rather than left for a reader to divide.
            "covered_pct": round(100 * len(shared) / len(mine)) if mine else 0,
        })
    return sorted(out, key=lambda g: -g["only_apprenticeship"])


def routes() -> dict:
    """The two ways into an occupation, and what only one of them reaches."""
    apprentice = crossings(RAPIDS_URL, RAPIDS_LOCAL)
    programme = crossings(CIP_URL, CIP_LOCAL)

    a_onet = {onet for _, onet in apprentice}
    p_onet = {onet for _, onet in programme}
    # The sentinel is excluded from EVERY side, not only ours. `our_soc()`
    # dropped it and these did not, so a `99-9999.00` row in either O*NET file
    # landed in `apprentice_soc` and, absent from `programme_soc`, counted as
    # apprenticeship-only — the headline figure, and the same defect
    # edtech-kg#70 fixed on the NCES file.
    a_soc = {soc_of(o) for o in a_onet} - {NO_MATCH}
    p_soc = {soc_of(o) for o in p_onet} - {NO_MATCH}
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
        # **Against O*NET's programme crosswalk, which is NOT the one this
        # graph loads.** That distinction is the whole finding: every code in
        # this set is in `ours`, measured below as
        # `apprenticeship_only_vs_ours`, which is 0. The two crosswalks
        # disagree; apprenticeship reaches nothing the loaded one misses.
        "apprenticeship_only": sorted(a_soc - p_soc),
        # The same question asked of the crosswalk this repo actually loads.
        # Reported beside the other one so a reader cannot take either for the
        # other, and so the page cannot quote one under a sentence about the
        # other again.
        "apprenticeship_only_vs_ours": sorted(a_soc - ours),
        "programme_only": len(p_soc - a_soc),
        "our_crosswalk_soc": len(ours),
        "apprenticeable_in_ours": len(a_soc & ours),
        "apprentice_soc_missing_from_ours": sorted(a_soc - ours),
        # Re-measured here rather than cited: every O*NET-SOC code carries a
        # suffix, so a naive join against SOC finds nothing at all.
        "naive_string_matches": len(a_onet & ours),
        "by_major_group": by_major_group(a_soc, p_soc),
    }


def probe(quiet: bool = False, with_reach: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    found = routes()
    # In the try, like everything else `main` reports as `refused:`. A network
    # failure under `--reach` raised `MalformedSource` straight past the
    # handler, so the one flag that goes to the network was the one path that
    # tracebacked.
    reach = reachable(RAPIDS_URL) if with_reach else []

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
              "   <- vs O*NET's programme crosswalk")
        print(f"  ... and not in OUR crosswalk     "
              f"{len(found['apprenticeship_only_vs_ours']):>8}"
              "   <- the one this graph loads")
        print(f"  reachable ONLY by a programme    {found['programme_only']:>8,}")

        print("\nWhere the apprenticeship-only occupations sit\n")
        # LABELLED. `also`/`only`/`cov` are measured against O*NET's
        # programme crosswalk, the same as the 63 two lines up — and those two
        # lines say so while this table did not, so a reader could take these
        # for the loaded-crosswalk figures, which are 0 by definition.
        print("  columns below are against O*NET's programme crosswalk, "
              "not the one this graph loads")
        print(f"  {'SOC major group':<38} {'appr':>5} {'also':>5} {'only':>5} {'cov':>5}")
        for g in found["by_major_group"]:
            if g["only_apprenticeship"] or g["apprenticeable"] >= 20:
                print(f"  {g['name'][:37]:<38} {g['apprenticeable']:>5} "
                      f"{g['also_via_a_programme']:>5} {g['only_apprenticeship']:>5} "
                      f"{g['covered_pct']:>4}%")

        print("\nJoining to the crosswalk this repo loads\n")
        print(f"  SOC our crosswalk carries        {found['our_crosswalk_soc']:>8,}")
        print(f"  of those, apprenticeable         {found['apprenticeable_in_ours']:>8,}")
        print(f"  apprenticeship SOC not in ours   "
              f"{len(found['apprentice_soc_missing_from_ours']):>8}")
        print(f"  naive O*NET-SOC = SOC matches    {found['naive_string_matches']:>8}"
              f"   of {found['apprentice_onet']:,}  <- the suffix")

        if with_reach:
            print("\nWhat answers a request\n")
            print(f"  {'source':<30} {'identified':<28} anonymous")
            for row in reach:
                anon = row["status_anonymous"] or "—"
                print(f"  {row['source']:<30} {str(row['status'])[:27]:<28} {anon}")
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
        # `--reach` only. It used to be forced on by `--json` too, which
        # made the machine-readable mode take the slow network path the
        # help text says is off by default — a flag doing something its
        # own documentation denies.
        result = probe(quiet=args.json, with_reach=args.reach)
    except MalformedSource as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    except zipfile.BadZipFile as exc:
        # A truncated download from a previous run leaves a file that exists
        # and is not a zip, and `download()` returns the cache without looking.
        # It raised straight past every handler as a traceback.
        print(f"refused: a cached file under data/ is not a readable archive "
              f"({exc}). Delete it and re-run.", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
