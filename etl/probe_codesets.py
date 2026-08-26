"""Probe the code sets this graph joins on — hierarchy, revision, and O*NET.

Two issues, one question: **can the graph survive a code-set change?**
edtech-kg#36 asks about CIP and SOC hierarchy, their revisions, and whether
O*NET-SOC is safe to join to SOC. edtech-kg#35 asks whether Career Clusters —
the language US high schools actually speak — is usable at all.

    python -m etl.probe_codesets            # the tables
    python -m etl.probe_codesets --json     # machine-readable

Three things are measured and one is read:

  * the CIP hierarchy present in the crosswalk this repo already loads;
  * the O*NET-SOC to SOC crosswalk, fetched from O*NET Center;
  * how those two taxonomies actually line up;
  * and the Career Clusters licence position, which is a reading rather than a
    measurement and is labelled as one.

**No third-party dependency**, as with the other probes.

The number this exists to produce is the O*NET one: a naive join between
O*NET-SOC and SOC matches **nothing at all**, which is the good case. The
dangerous version of that finding would have been a partial match.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from etl import probe_cipsoc as crosswalk

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ONET_URL = "https://www.onetcenter.org/dl_files/OccupationalListings.zip"
ONET_LOCAL = DATA_DIR / "OccupationalListings.zip"
ONET_MEMBER = "OccupationalListings/Crosswalks/2019_to_SOC_Crosswalk.xlsx"

CLUSTERS = "https://careertech.org/career-clusters/"

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# The crosswalk's own NO MATCH sentinel, excluded here for the reason
# edtech-kg#70 established: it is not an occupation.
NO_MATCH = "99-9999"

# A CIP code that names a whole 2-digit family, and one that names a 4-digit
# series. Both are ROLLUP rows rather than programmes.
FAMILY = re.compile(r"\A\d{2}\.0000\Z")
SERIES = re.compile(r"\A\d{2}\.\d{2}00\Z")


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
            f"{url} did not return an archive — got {payload[:40]!r}")
    into.parent.mkdir(parents=True, exist_ok=True)
    into.write_bytes(payload)
    return payload


def crosswalk_pairs() -> list[tuple[str, str]]:
    """The CIP-SOC pairs, from a workbook this function makes sure exists.

    `data/` is gitignored, so on a clean checkout the file is absent and
    `zipfile.ZipFile(crosswalk.LOCAL)` raised `FileNotFoundError` — a
    traceback, since `main()` catches only `MalformedSource`. That is the
    first thing anyone reproducing these figures would have hit.
    """
    if not crosswalk.LOCAL.exists():
        try:
            crosswalk.download()
        except (RuntimeError, ValueError) as exc:
            raise MalformedSource(f"could not fetch the CIP-SOC crosswalk: {exc}") from exc
    with zipfile.ZipFile(crosswalk.LOCAL) as book:
        rows = crosswalk.rows(book, crosswalk.sheets(book)["CIP-SOC"])
    mapped, _ = crosswalk.pairs(rows, crosswalk.find_header(rows, "CIP"))
    return mapped


def crosswalk_soc(mapped: list[tuple[str, str]] | None = None) -> set[str]:
    """The SOC codes our crosswalk reaches, minus the NO MATCH sentinel."""
    if mapped is None:
        mapped = crosswalk_pairs()
    return {soc for _, soc in mapped if soc != NO_MATCH}


def cip_hierarchy(mapped: list[tuple[str, str]] | None = None) -> dict:
    """What the crosswalk carries above the leaf level — which is not much.

    edtech-kg#36 says `probe_cipsoc.py` "sees only leaves". Measured, it is
    worse than that: it sees a MIXTURE. Some families have a rollup row and
    most do not, so code that looks one up works for a few and returns nothing
    for the rest — which is harder to notice than a uniform absence.
    """
    mapped = mapped if mapped is not None else crosswalk_pairs()
    codes = sorted({cip for cip, _ in mapped})

    families = sorted({c for c in codes if FAMILY.match(c)})
    series = sorted({c for c in codes if SERIES.match(c) and not FAMILY.match(c)})
    prefixes = {c[:2] for c in codes}
    with_row = {c[:2] for c in families}

    return {"codes": len(codes),
            "family_rows": len(families),
            "series_rows": len(series),
            "leaf_rows": len(codes) - len(families) - len(series),
            "distinct_families": len(prefixes),
            "families_with_a_row": len(with_row),
            "families_without_a_row": sorted(prefixes - with_row),
            # The question #36 asks in a parenthesis. The 2-digit prefix is in
            # the code string, so the family CODE is derivable — but its NAME
            # is not, for any family with no rollup row. That is what makes the
            # separate NCES hierarchy file necessary rather than convenient.
            "family_names_derivable": not (prefixes - with_row)}


def onet_to_soc(ours: set[str] | None = None) -> dict:
    """Whether O*NET-SOC can be joined to SOC, and what happens if you try.

    `ours` is the SOC side of the CIP-SOC crosswalk. It is a parameter so that
    `probe()` can read that workbook once instead of once per function.
    """
    with zipfile.ZipFile(io.BytesIO(download(ONET_URL, ONET_LOCAL))) as archive:
        try:
            member = archive.read(ONET_MEMBER)
        except KeyError as exc:
            raise MalformedSource(
                f"{ONET_MEMBER} is not in the O*NET archive — it holds "
                f"{archive.namelist()[:6]}. The layout has changed.") from exc

    with zipfile.ZipFile(io.BytesIO(member)) as book:
        # The SAME reader `probe_cipsoc` uses, not a second one. It places
        # cells by their `r` attribute; a reader that appends in document
        # order puts the 2018 SOC *Title* in the column the header calls
        # 2018 SOC Code the moment a row omits its title cell, and every
        # figure below stays plausible and is wrong. Measured on the file as
        # it stands today: every row is dense and the two readers agree
        # exactly, so this is a latent defect rather than a live one — which
        # is precisely why it needs the shared reader and not a comment.
        parts = crosswalk.sheets(book)
        if len(parts) != 1:
            raise MalformedSource(
                f"the O*NET crosswalk holds {sorted(parts)} — refusing to "
                f"guess which sheet carries the mapping")
        rows = crosswalk.rows(book, next(iter(parts.values())))

    head = next((i for i, r in enumerate(rows)
                 if any("O*NET-SOC" in c and "Code" in c for c in r)), None)
    if head is None:
        raise MalformedSource("no header row in the O*NET crosswalk")
    body = [r for r in rows[head + 1:] if len(r) > 2 and r[0].strip()]
    if not body:
        raise MalformedSource("the O*NET crosswalk parsed to zero rows")

    onet_codes = {r[0].strip() for r in body}
    rolled = {r[2].strip() for r in body}
    fan = Counter(r[2].strip() for r in body)

    if ours is None:
        ours = crosswalk_soc()

    return {"source": ONET_URL,
            "onet_occupations": len(onet_codes),
            "soc_codes_they_roll_up_to": len(rolled),
            "soc_codes_in_our_crosswalk": len(ours),
            "in_onet_not_ours": sorted(rolled - ours),
            "in_ours_not_onet": sorted(ours - rolled),
            # The finding. Every O*NET code carries a `.NN` suffix, so string
            # equality against a SOC code matches nothing — which is the SAFE
            # failure. A partial match would have been the dangerous one.
            "naive_string_matches": len(onet_codes & ours),
            "soc_with_one_occupation": sum(1 for v in fan.values() if v == 1),
            "soc_with_several": sum(1 for v in fan.values() if v > 1),
            "largest_fan_out": max(fan.values()) if fan else 0}


def career_clusters() -> dict:
    """Read rather than measured — the licence question edtech-kg#35 asks.

    Everything here is quoted from the page as it stood on the retrieval date,
    because a licence position is a fact about a document and not about data.

    Deliberately not cached on disk, unlike the two workbooks: a licence
    position is exactly the thing that should be re-read rather than served
    from a copy taken months ago. The cost is one request per run.
    """
    request = urllib.request.Request(CLUSTERS, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            page = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{CLUSTERS} did not answer ({exc})") from exc

    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    # Periods allowed: the notice reads "© 2023 Advance CTE: State Leaders
    # Connecting Learning to Work. All rights reserved." and a pattern that
    # stopped at the first full stop found nothing — reporting no notice on a
    # page that carries one, which is the wrong way round for a licence check.
    notice = re.search(r"(©\s*\d{4}[^©]{0,160}?All rights reserved)", flat)
    structure = re.search(r"(\d+) Clusters and (\d+) Sub-Clusters", flat)
    # Either quote style, and a query string or fragment allowed after the
    # extension. The tight pattern (double quotes, extension at the very end)
    # reported zero for href='/x.xlsx?v=2' — and the zero here feeds a licence
    # conclusion, so a false negative is the wrong way round, the same way
    # round as the copyright pattern above.
    machine_readable = sorted(set(re.findall(
        r"""href=["']([^"']*\.(?:xlsx|xls|csv|json))(?:[?#][^"']*)?["']""",
        page, re.I)))

    return {"source": CLUSTERS,
            "copyright_notice": notice.group(1).strip() if notice else None,
            "clusters": int(structure.group(1)) if structure else None,
            "sub_clusters": int(structure.group(2)) if structure else None,
            "machine_readable_files": machine_readable,
            "measured_or_read": "read"}


def probe(quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Read once, used by both: the workbook was being opened and its pairs
    # recomputed a second time inside onet_to_soc().
    mapped = crosswalk_pairs()
    cip = cip_hierarchy(mapped)
    onet = onet_to_soc(crosswalk_soc(mapped))
    clusters = career_clusters()

    if not quiet:
        print("\nCIP hierarchy — what the crosswalk carries above the leaf\n")
        print(f"  CIP codes in the crosswalk       {cip['codes']:>8,}")
        print(f"    6-digit leaves                 {cip['leaf_rows']:>8,}")
        print(f"    4-digit series rows            {cip['series_rows']:>8}")
        print(f"    2-digit family rows            {cip['family_rows']:>8}")
        print(f"  distinct 2-digit families        {cip['distinct_families']:>8}")
        print(f"    with a family-level row        {cip['families_with_a_row']:>8}")
        print(f"    WITHOUT one                    {len(cip['families_without_a_row']):>8}")
        print("  -> the family CODE is in the string; its NAME is not, for those "
              f"{len(cip['families_without_a_row'])}.")
        print("     The separate NCES hierarchy file is necessary, not optional.")

        print("\nO*NET-SOC against SOC\n")
        print(f"  O*NET occupations                {onet['onet_occupations']:>8,}")
        print(f"  SOC codes they roll up to        {onet['soc_codes_they_roll_up_to']:>8,}")
        print(f"  SOC codes our crosswalk carries  {onet['soc_codes_in_our_crosswalk']:>8,}")
        print(f"  in O*NET and not ours            {len(onet['in_onet_not_ours']):>8}")
        print(f"  in ours and not O*NET            {len(onet['in_ours_not_onet']):>8}")
        print(f"  naive string-equality matches    {onet['naive_string_matches']:>8}"
              f"   of {onet['onet_occupations']:,}")
        print(f"  SOC codes with several O*NET occupations {onet['soc_with_several']:>3}"
              f"   (largest fan-out {onet['largest_fan_out']})")

        print("\nCareer Clusters — read, not measured\n")
        print(f"  structure                        {clusters['clusters']} clusters, "
              f"{clusters['sub_clusters']} sub-clusters")
        print(f"  copyright notice                 {clusters['copyright_notice']}")
        print(f"  machine-readable files published {len(clusters['machine_readable_files']):>8}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_codesets\n")

    return {"retrieved_at": stamp, "cip_hierarchy": cip,
            "onet": onet, "career_clusters": clusters}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json)
    except MalformedSource as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
