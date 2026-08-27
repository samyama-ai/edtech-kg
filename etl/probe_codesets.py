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

# BOTH pages, because the licence conclusion needs both. The framework landing
# page carries the structure and the copyright notice; the CROSSWALKS page is
# the one the document's own corroborating sentence describes, and it was never
# fetched — so "0 machine-readable files" was counted on one page while the
# sentence beside it pointed at another.
CLUSTERS = "https://careertech.org/career-clusters/"
CLUSTER_CROSSWALKS = "https://careertech.org/crosswalks/"

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
        except MalformedSource:
            raise
        except Exception as exc:  # noqa: BLE001 - see below
            # EVERYTHING, not `RuntimeError`/`ValueError` — neither of which
            # a download raises. `URLError`, `OSError`, `TimeoutError` and
            # `BadZipFile` are all reachable, so the guard covered the case
            # that cannot happen and missed the ones that do.
            raise MalformedSource(
                f"could not fetch the CIP-SOC crosswalk "
                f"({type(exc).__name__}): {exc}") from exc
    # The READ is wrapped too, not only the fetch. A fetch that returns
    # without writing a usable file — truncated, HTML, a cached partial —
    # then raises `FileNotFoundError` or `BadZipFile`, which `main()` does not
    # catch, so the traceback this function prevents came back through the
    # door next to the one that was closed. `KeyError` too: that is how a
    # renamed sheet arrives.
    try:
        with zipfile.ZipFile(crosswalk.LOCAL) as book:
            rows = crosswalk.rows(book, crosswalk.sheets(book)["CIP-SOC"])
        mapped, _ = crosswalk.pairs(rows, crosswalk.find_header(rows, "CIP"))
    except MalformedSource:
        raise
    except KeyError as exc:
        raise MalformedSource(
            f"the CIP-SOC workbook has no {exc} sheet — NCES has renamed or "
            f"restructured it, and every figure below reads that sheet.") from exc
    except Exception as exc:  # noqa: BLE001 - main() catches MalformedSource only
        raise MalformedSource(
            f"the CIP-SOC workbook at {crosswalk.LOCAL} could not be read "
            f"({type(exc).__name__}): {exc}. Delete it and re-run to fetch a "
            f"fresh copy.") from exc
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
            # The question #36 asks in a parenthesis. Named for what it
            # measures — every family having a rollup ROW — rather than
            # `family_names_derivable`, which read as the opposite of the
            # argument: the family CODE is always derivable from the string,
            # and it is the NAME that is missing without a row. That is what
            # makes the separate NCES hierarchy file necessary.
            "every_family_has_a_row": not (prefixes - with_row)}


def column_named(header: list[str], *must_contain: str, avoid: str = "") -> int:
    """The index of the column whose heading names these things.

    Named rather than positional, and it refuses rather than guessing: a
    heading that has moved is a layout change, and reading the old index would
    keep working while counting the wrong column.
    """
    matched = []
    for i, cell in enumerate(header):
        if all(token in cell for token in must_contain):
            if avoid and avoid in cell:
                continue
            matched.append(i)
    if len(matched) > 1:
        # AMBIGUOUS, not "the first one". A heading reading "SOC Code and
        # Title" satisfies both the code and the title lookup, so two figures
        # would be read off one column — the positional read this function
        # exists to replace, arriving by another route.
        raise MalformedSource(
            f"{len(matched)} columns are headed {' + '.join(must_contain)}"
            f"{f' (excluding {avoid})' if avoid else ''}: "
            f"{[header[i] for i in matched]}. Reading the first would take two "
            f"figures from one column.")
    if matched:
        return matched[0]
    raise MalformedSource(
        f"no column headed {' + '.join(must_contain)}"
        f"{f' (excluding {avoid})' if avoid else ''} in {header} — the "
        f"crosswalk layout has changed and the figures need re-checking "
        f"rather than re-reading")


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

    # BOTH columns found by name. The O*NET column was looked up by heading
    # while the SOC column was read at a hardcoded `r[2]` — so the file was
    # half-trusted to keep its layout, and the half that was trusted is the
    # one carrying the codes every figure below rests on. This file has four
    # columns today, and reading the third by index keeps working, wrongly, if
    # a fifth arrives.
    onet_at = column_named(rows[head], "O*NET-SOC", "Code")
    soc_at = column_named(rows[head], "SOC", "Code", avoid="O*NET")

    body = [r for r in rows[head + 1:]
            if len(r) > max(onet_at, soc_at) and r[onet_at].strip()]
    if not body:
        raise MalformedSource("the O*NET crosswalk parsed to zero rows")

    # The SOC title too, so the example the page gives is printed rather than
    # written down. The page named `15-1299 Computer Occupations, All Other`
    # and the probe emitted only the count — so the one concrete illustration
    # of the fan-out was the one figure on the page nobody could reproduce.
    title_at = column_named(rows[head], "SOC", "Title", avoid="O*NET")
    titles = {r[soc_at].strip(): r[title_at].strip() for r in body
              if len(r) > title_at}

    onet_codes = {r[onet_at].strip() for r in body}
    rolled = {r[soc_at].strip() for r in body}
    fan = Counter(r[soc_at].strip() for r in body)

    if ours is None:
        ours = crosswalk_soc()

    widest = max(fan, key=fan.get) if fan else None

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
            # Computed once. It was `max(fan, key=fan.get)` three times over,
            # and two of those were on the same line as each other.
            "soc_with_one_occupation": sum(1 for v in fan.values() if v == 1),
            "soc_with_several": sum(1 for v in fan.values() if v > 1),
            "largest_fan_out": max(fan.values()) if fan else 0,
            "widest_soc": widest,
            "widest_soc_title": titles.get(widest) if widest else None}


def page_text(url: str) -> str:
    """One page, or a refusal naming it."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc


def data_files(page: str) -> list[str]:
    """Links to a machine-readable data file on one page.

    Either quote style, and a query string or fragment allowed after the
    extension. The tight pattern (double quotes, extension at the very end)
    reported zero for `href='/x.xlsx?v=2'` — and a zero here feeds a licence
    conclusion, so a false negative is the wrong way round, the same way round
    as the copyright pattern.

    The opening quote is backreferenced, so `href="a.csv'` no longer matches.
    """
    return sorted(set(match[1] for match in re.findall(
        # `(?!\1)` rather than `[^"']`: a double-quoted href may contain an
        # apostrophe — `href="/o'brien.csv"` — and excluding both quote
        # characters missed it. Only the delimiter that opened the attribute
        # can close it, and a missed file is a false zero.
        r"""href=(["'])((?:(?!\1)[^\s>])*\.(?:xlsx|xls|csv|json))"""
        r"""(?:[?#](?:(?!\1)[^\s>])*)?\1""",
        page, re.I)))


def career_clusters() -> dict:
    """Read rather than measured — the licence question edtech-kg#35 asks.

    Everything here is quoted from the page as it stood on the retrieval date,
    because a licence position is a fact about a document and not about data.

    Deliberately not cached on disk, unlike the two workbooks: a licence
    position is exactly the thing that should be re-read rather than served
    from a copy taken months ago. The cost is one request per run.
    """
    page = page_text(CLUSTERS)
    crosswalks = page_text(CLUSTER_CROSSWALKS)
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    # Periods allowed: the notice reads "© 2023 Advance CTE: State Leaders
    # Connecting Learning to Work. All rights reserved.", and stopping at the
    # first full stop reported no notice on a page that carries one.
    notice = re.search(r"(©\s*\d{4}[^©]{0,160}?All rights reserved)", flat)
    structure = re.search(r"(\d+) Clusters and (\d+) Sub-Clusters", flat)
    # Either quote style, and a query string or fragment allowed after the
    # extension. The tight pattern (double quotes, extension at the very end)
    # reported zero for href='/x.xlsx?v=2' — and the zero here feeds a licence
    # conclusion, so a false negative is the wrong way round, the same way
    # round as the copyright pattern above.
    # REFUSED when the page carries neither landmark.
    #
    # Nothing here validated what came back, unlike `download()`, which checks
    # for the PK magic before believing it has a workbook. A redirect, a cookie
    # wall or a JavaScript shell returns HTTP 200 and no content: `notice` and
    # `structure` are both None, `data_files` is empty, and the probe printed
    # "None clusters, None sub-clusters" and "data files ... 0" without
    # complaint.
    #
    # That zero is what `docs/sources/code-sets.md` rests its "NOT cleared"
    # licence position on. A genuine absence of machine-readable files and a
    # failed fetch produce the same zero, and nothing on the page or in the
    # output tells a reader — or a re-run six months from now — which one it
    # saw. A licence conclusion is the last thing that should rest on a number
    # with two meanings.
    #
    # BOTH must be missing to refuse, not either. Advance CTE can reword a
    # copyright line or restate the cluster count without the page having
    # failed to load, and refusing on one missing landmark would turn an
    # ordinary edit into a broken probe.
    # BOTH pages. The guard below covered `CLUSTERS` only, and the crosswalks
    # page is where both corroborating figures come from — a failed load there
    # returned two empty lists, so the zero the licence position rests on was
    # still reachable from a page that never loaded. Guarding one of two pages
    # that feed a conclusion is not guarding the conclusion.
    #
    # It carries no cluster count and no copyright line, so it is checked on
    # what it does carry: links to published files. None at all is the same
    # failed-fetch signal.
    # Query string or fragment allowed, like `data_files` and the PDF regex.
    # Without it a page whose links all look like `/wheel.pdf?ver=3` is
    # refused as carrying none — a false refusal of a page that loaded.
    if not re.search(
            r"""href=["'][^"']+\.(?:pdf|xlsx|xls|csv|json|docx?)(?:[?#][^"']*)?["']""",
            crosswalks, re.I):
        raise MalformedSource(
            f"{CLUSTER_CROSSWALKS} carried no links to published files at all "
            f"({len(crosswalks)} characters). That page is where the PDF count "
            f"and the crosswalks-page zero both come from, so a failed load "
            f"there produces the same numbers as a genuine absence — and the "
            f"licence position is argued from exactly those numbers.")

    if notice is None and structure is None:
        raise MalformedSource(
            f"{CLUSTERS} carried neither the copyright notice nor the "
            f"'N Clusters and M Sub-Clusters' line ({len(flat)} characters of "
            f"text). Both are on the page this probe reads, so their joint "
            f"absence means what came back is not that page — a redirect, a "
            f"cookie wall or a script shell. Refusing rather than reporting "
            f"the zero it would otherwise produce, because that zero is what "
            f"the licence position is argued from.")

    machine_readable = data_files(page)
    on_crosswalks = data_files(crosswalks)
    return {"source": CLUSTERS,
            "crosswalks_source": CLUSTER_CROSSWALKS,
            "copyright_notice": notice.group(1).strip() if notice else None,
            "clusters": int(structure.group(1)) if structure else None,
            "sub_clusters": int(structure.group(2)) if structure else None,
            # Per page. The conclusion rests on the crosswalks page, so the
            # count from that page is the one the document quotes.
            "machine_readable_files": machine_readable,
            "machine_readable_on_crosswalks": on_crosswalks,
            # What IS published there, which is the corroboration: the
            # document says PDFs, so the PDFs are counted rather than
            # described.
            # Backreferenced, and a query string or fragment allowed after
            # the extension — the same two rules as `data_files`, which this
            # regex is the corroborating half of. It carried a comment
            # claiming parity with `data_files` while missing the query-string
            # allowance, so `/wheel.pdf?ver=3` was not counted and the "6 PDFs"
            # could under-report the thing that corroborates the zero.
            "pdfs_on_crosswalks": sorted({
                match[1].rsplit("/", 1)[-1].split("?")[0].split("#")[0]
                for match in re.findall(
                    r"""href=(["'])((?:(?!\1)[^\s>])*\.pdf(?:[?#](?:(?!\1)[^\s>])*)?)\1""",
                    crosswalks, re.I)}),
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
        print(f"  SOC codes with several O*NET occupations {onet['soc_with_several']:>3}")
        print(f"  widest: {onet['widest_soc']} {str(onet['widest_soc_title'])[:38]}"
              f" -> {onet['largest_fan_out']} O*NET occupations")

        print("\nCareer Clusters — read, not measured\n")
        print(f"  structure                        {clusters['clusters']} clusters, "
              f"{clusters['sub_clusters']} sub-clusters")
        print(f"  copyright notice                 {clusters['copyright_notice']}")
        print(f"  data files on the framework page {len(clusters['machine_readable_files']):>8}")
        print(f"  data files on the CROSSWALKS page{len(clusters['machine_readable_on_crosswalks']):>8}"
              "   <- the page the licence conclusion rests on")
        print(f"  PDFs published there instead     {len(clusters['pdfs_on_crosswalks']):>8}")
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
    except zipfile.BadZipFile as exc:
        # `download()` returns a cached file without looking inside it, so a
        # truncated download from a previous run raised past every handler as a
        # traceback — the failure `crosswalk_pairs` was fixed for, through the
        # other door.
        print(f"refused: a cached file under data/ is not a readable archive "
              f"({exc}). Delete it and re-run.", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
