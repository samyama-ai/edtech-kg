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
import subprocess
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
    # Named individually rather than summarised. The page said "404 on every
    # standard CKAN endpoint" while one endpoint was probed.
    ("data.gov CKAN package_list",
     "https://catalog.data.gov/api/3/action/package_list"),
    ("data.gov CKAN package_search",
     "https://catalog.data.gov/api/3/action/package_search?q=apprenticeship"),
    # CONTROL hosts. Both pages argue that the failures above are not a general
    # egress problem, and cite these as reached in the same session — so they
    # have to be in the same run rather than in a sentence.
    ("control: onetcenter.org", "https://www.onetcenter.org/"),
    ("control: nces.ed.gov", "https://nces.ed.gov/"),
    ("control: careertech.org", "https://careertech.org/"),
    ("O*NET RAPIDS crosswalk", RAPIDS_URL),
]

# Queried alongside the system resolver. The page's whole argument rests on
# telling "this network cannot resolve it" apart from "it resolves nowhere",
# and one `gethostbyname()` call cannot make that distinction.
PUBLIC_RESOLVERS = (("Google", "8.8.8.8"), ("Cloudflare", "1.1.1.1"))


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
        except (RuntimeError, ValueError, urllib.error.URLError,
                TimeoutError, OSError) as exc:
            # A network failure escaped as a traceback: the crosswalk
            # download raises URLError, and only RuntimeError and
            # ValueError were caught.
            raise MalformedSource(
                f"could not fetch the CIP-SOC crosswalk: {exc}") from exc
    with zipfile.ZipFile(crosswalk.LOCAL) as book:
        table = rows(book, sheets(book)["CIP-SOC"])
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
    # dropped it and these two did not, so a `99-9999.00` row in either O*NET
    # crosswalk would have landed in `apprentice_soc` and, being absent from
    # `programme_soc`, been reported as an occupation reachable ONLY by
    # apprenticeship. That is the headline figure, and it is the same class of
    # defect edtech-kg#70 fixed on the NCES file.
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
        "by_major_group": by_major_group(a_soc, p_soc),
    }


def resolves_anywhere(host: str) -> dict:
    """Ask the system resolver AND two public ones.

    The pages distinguish "this network cannot reach it" from "it resolves
    nowhere", and only the second can be asserted without qualification. One
    `gethostbyname()` call cannot tell those apart — it was the system resolver
    once, while the page claimed "no A record from any resolver".

    Answered without a DNS library: `dig` is asked directly, so this stays
    dependency-free like every other probe here. A resolver that cannot be
    reached is recorded as unknown rather than as a negative, because "we could
    not ask" is not "there is no record".
    """
    answers = {}
    try:
        answers["system"] = socket.gethostbyname(host)
    except OSError:
        answers["system"] = None

    for name, server in PUBLIC_RESOLVERS:
        try:
            out = subprocess.run(["dig", "+short", f"@{server}", host],
                                 capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            answers[name] = "unknown"
            continue
        if out.returncode != 0:
            answers[name] = "unknown"
            continue
        found = [line for line in out.stdout.split()
                 if line and not line.endswith(".")]
        answers[name] = found[0] if found else None

    # The strong claim needs a PUBLIC resolver to have answered. A local
    # failure with both public resolvers unreachable is "we could not ask" —
    # and reading that as "there is no record" turns a machine with no `dig`,
    # or no route to 8.8.8.8, into evidence about a publisher.
    public = [answers[name] for name, _ in PUBLIC_RESOLVERS
              if answers.get(name) != "unknown"]
    answered = [v for v in answers.values() if v != "unknown"]
    return {"by_resolver": answers,
            "resolves_nowhere": bool(public) and all(v is None for v in answered)}


def reachable() -> list[dict]:
    """What answers a request, and what does not — attempted, not remembered.

    DNS is resolved separately from the connection, because they fail
    differently and the difference is the whole finding. A host that resolves
    and refuses TCP is a source that will not talk to this network; a host
    whose name resolves NOWHERE is a broken chain at the publisher's end, and
    only the second can be asserted without qualification.
    """
    # Resolved once per HOST, not once per row. `REACH` lists two data.gov
    # endpoints and two onetcenter URLs, and each resolution shells out to
    # `dig` twice at up to 20s — so a repeated host paid the whole cost again
    # for an answer already in hand.
    #
    # Scoped to this call rather than cached on the module: a cache that
    # outlives the run answers a later question with an earlier network, which
    # is the opposite of what a probe re-measuring every run is for.
    resolved: dict[str, dict] = {}
    out = []
    for name, url in REACH:
        host = urllib.parse.urlparse(url).hostname or ""
        if host not in resolved:
            resolved[host] = resolves_anywhere(host)
        dns = resolved[host]
        record = {"source": name, "url": url,
                  "dns": dns["by_resolver"].get("system"),
                  "by_resolver": dns["by_resolver"],
                  "status": None, "status_anonymous": None}

        if dns["resolves_nowhere"]:
            record["status"] = "name does not resolve (no resolver has a record)"
            out.append(record)
            continue
        if record["dns"] is None:
            record["status"] = ("name does not resolve here (another resolver "
                                "does, so this is local)")
            out.append(record)
            continue

        # BOTH requests, because the pages turn on the difference. `bls.gov`
        # returned 403 to a short or absent User-Agent and 200 to the
        # identifying one — a block on anonymity. A source that returns 403 to
        # both is blocking automation instead, and that is a different claim
        # which the pages make and this used to not measure.
        record["status"] = attempt(url, USER_AGENT)
        record["status_anonymous"] = attempt(url, None)
        out.append(record)
    return out


def attempt(url: str, agent: str | None) -> str:
    """One HEAD, with or without an identifying User-Agent.

    HEAD rather than GET, and the pages say so: a 405 or 403 to HEAD is not
    evidence about GET, and this whole probe is about telling failure modes
    apart.
    """
    headers = {"User-Agent": agent} if agent else {}
    request = urllib.request.Request(url, headers=headers, method="HEAD")
    if agent is None:
        # urllib inserts `Python-urllib/3.x` unless it is removed outright, so
        # "anonymous" would otherwise measure a DEFAULT agent and not an
        # absent one — the same trap edtech-kg#37 recorded on bls.gov.
        request.add_unredirected_header("User-Agent", "")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return str(response.status)
    except urllib.error.HTTPError as exc:
        return str(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"no connection ({getattr(exc, 'reason', exc)})"


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

        print("\nWhere the apprenticeship-only occupations sit\n")
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
