"""Which identifier names a US institution, and what bridges to it — #45.

IPEDS `UNITID`, `OPEID`, and anything published by ROR, Wikidata or a state all
name the same college differently, and colleges merge, close and reopen under
new numbers. Deciding the canonical identifier before loading costs an
afternoon; discovering it afterwards costs a reconciliation pass.

    python -m etl.probe_institution_identity            # cardinality and closures
    python -m etl.probe_institution_identity --bridges  # also ROR and Wikidata
    python -m etl.probe_institution_identity --record

`--bridges` is separate because it reaches two more publishers. The Wikidata
endpoint rate-limits, so it is retried with backoff rather than reported as
absent — a 429 recorded as "no coverage" would be a measurement of our own
impatience.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter

from etl.identity import USER_AGENT

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "institution-identity-measured.json"

RECORD_NOTE = (
    "One measured run of `python -m etl.probe_institution_identity --bridges "
    "--record`, committed so docs/sources/institution-identity.md can be "
    "checked without downloading IPEDS or querying Wikidata.")

#: Institutional characteristics — the file carrying both identifiers, the
#: closure date and the successor pointer.
DIRECTORY = "https://nces.ed.gov/ipeds/datacenter/data/HD2022.zip"

#: IPEDS writes this where a value does not apply. It is not a number and it is
#: not missing data — it is a sentinel, and a loader that reads it as either
#: gets a different answer. `99-9999 NO MATCH` cost this repo a count once
#: already (#70); this is the same shape in a different collection.
SENTINEL = "-2"

WIKIDATA = "https://query.wikidata.org/sparql"
#: P1771 is Wikidata's IPEDS identifier property.
IPEDS_ITEMS = "SELECT (COUNT(DISTINCT ?i) AS ?n) WHERE { ?i wdt:P1771 ?x }"
ROR = "https://api.ror.org/v2/organizations?filter=country.country_code:US&page={page}"


class Unreachable(Exception):
    """A source that did not answer. Never recorded as an absence — "no
    coverage" and "we could not ask" are different findings."""


def _open(url: str, timeout: int = 90, accept: str | None = None):
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=timeout)


def directory() -> list[dict]:
    """One year of institutional characteristics, read whole."""
    try:
        with _open(DIRECTORY, timeout=180) as response:
            blob = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Unreachable(f"{DIRECTORY} did not answer ({exc})") from exc

    with zipfile.ZipFile(io.BytesIO(blob)) as book:
        base = [m for m in book.namelist() if not m.lower().endswith("_rv.csv")]
        if len(base) != 1:
            raise Unreachable(f"expected one unrevised member, found {book.namelist()}")
        with book.open(base[0]) as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8",
                                                     errors="replace"))
            reader.fieldnames = [c.lstrip("﻿") for c in reader.fieldnames]
            return list(reader)


def identity(rows: list[dict]) -> dict:
    """UNITID against OPEID, with the sentinel held apart from the data."""
    if not rows:
        raise Unreachable("the directory is empty — every figure below would be 0")

    unitids = {r["UNITID"] for r in rows}
    values = Counter(r["OPEID"].strip() for r in rows)
    sentinel = {v: n for v, n in values.items() if v == SENTINEL or not v}
    real = {v: n for v, n in values.items() if v not in sentinel}
    shared = {v: n for v, n in real.items() if n > 1}

    # How widely the sentinel is used, because a loader meeting it in one
    # column will meet it in others.
    columns = sum(1 for c in rows[0]
                  if any(r[c].strip() == SENTINEL for r in rows))

    return {"institutions": len(rows),
            "distinct_unitid": len(unitids),
            "unitid_is_unique": len(unitids) == len(rows),
            "distinct_real_opeid": len(real),
            "on_the_sentinel": sum(sentinel.values()),
            "opeids_shared_by_several": len(shared),
            "institutions_sharing_an_opeid": sum(shared.values()),
            "spread": {str(k): v for k, v in sorted(Counter(real.values()).items())},
            "columns_using_the_sentinel": columns,
            "total_columns": len(rows[0])}


def afterlife(rows: list[dict]) -> dict:
    """What IPEDS says about an institution that is no longer operating."""
    closed = [r for r in rows if r["CLOSEDAT"].strip() not in (SENTINEL, "")]
    successor = [r for r in rows
                 if r.get("NEWID", "").strip() not in ("", "0", SENTINEL)]
    return {"with_a_close_date": len(closed),
            "with_a_successor": len(successor),
            "with_both": len([r for r in successor
                              if r["CLOSEDAT"].strip() not in (SENTINEL, "")]),
            "not_currently_active": len([r for r in rows
                                         if r["CYACTIVE"].strip() != "1"]),
            "successor_targets": len({r["NEWID"].strip() for r in successor})}


def wikidata_coverage() -> int:
    """How many Wikidata items carry an IPEDS identifier.

    Retried with backoff. The endpoint returns 429 readily, and a 429 recorded
    as zero would publish our own rate limit as a fact about Wikidata.
    """
    url = f"{WIKIDATA}?format=json&query={urllib.parse.quote(IPEDS_ITEMS)}"
    for attempt in range(4):
        try:
            with _open(url, accept="application/sparql-results+json") as response:
                answer = json.load(response)
            return int(answer["results"]["bindings"][0]["n"]["value"])
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError):
            time.sleep(4 * (attempt + 1))
    raise Unreachable(
        "Wikidata did not answer after four attempts — recording that as zero "
        "coverage would publish our own rate limit as a fact about Wikidata")


def ror_external_ids(pages: int = 3) -> dict:
    """What ROR records point at, and whether IPEDS is among it."""
    types: Counter = Counter()
    seen = 0
    for page in range(1, pages + 1):
        try:
            with _open(ROR.format(page=page), timeout=60) as response:
                answer = json.load(response)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise Unreachable(f"ROR did not answer ({exc})") from exc
        for organisation in answer.get("items", []):
            seen += 1
            for external in organisation.get("external_ids", []):
                types[external.get("type")] += 1
        time.sleep(1)
    if not seen:
        raise Unreachable("ROR returned no organisations — a coverage figure "
                          "drawn from this would be a division by zero")
    return {"sampled": seen,
            "id_types": dict(types),
            "carries_ipeds": "ipeds" in {t.lower() for t in types if t},
            "carrying_wikidata": types.get("wikidata", 0)}


def probe(bridges: bool = False, quiet: bool = False) -> dict:
    rows = directory()
    result = {"source": DIRECTORY,
              "identity": identity(rows),
              "afterlife": afterlife(rows),
              "read_or_measured": "measured"}
    if bridges:
        result["ror"] = ror_external_ids()
        result["wikidata_items_with_an_ipeds_id"] = wikidata_coverage()

    if not quiet:
        i, a = result["identity"], result["afterlife"]
        print("\nInstitution identity — edtech-kg#45\n")
        print(f"  institutions                        {i['institutions']:>7,}")
        print(f"  UNITID unique per row               {str(i['unitid_is_unique']):>7}")
        print(f"  real OPEIDs                         {i['distinct_real_opeid']:>7,}")
        print(f"  carrying the {SENTINEL!r} sentinel instead     "
              f"{i['on_the_sentinel']:>7,}   <- not an identifier")
        print(f"  OPEIDs shared by several UNITIDs    {i['opeids_shared_by_several']:>7,}")
        print(f"  institutions in a shared OPEID      {i['institutions_sharing_an_opeid']:>7,}")
        print(f"  columns using {SENTINEL!r} somewhere        "
              f"{i['columns_using_the_sentinel']:>7,} of {i['total_columns']}")
        print()
        print(f"  with a close date                   {a['with_a_close_date']:>7,}")
        print(f"  with a successor pointer            {a['with_a_successor']:>7,}")
        print(f"  with BOTH                           {a['with_both']:>7,}"
              f"   <- closure and merger are disjoint")
        if bridges:
            print()
            print(f"  ROR sampled                         {result['ror']['sampled']:>7,}")
            print(f"  ROR carries an IPEDS id             "
                  f"{str(result['ror']['carries_ipeds']):>7}")
            print(f"  Wikidata items with an IPEDS id     "
                  f"{result['wikidata_items_with_an_ipeds_id']:>7,}")
        print()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--bridges", action="store_true",
                        help="also measure ROR and Wikidata coverage")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(bridges=args.bridges or args.record,
                       quiet=args.json or args.record)
    except Unreachable as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.record:
        RECORD.parent.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(
            json.dumps({"_": RECORD_NOTE, **result}, indent=2,
                       ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {RECORD.relative_to(ROOT)}")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
