"""Measure what the CEDS ontology defines — edtech-kg#29.

    python -m etl.probe_ceds             # the tables
    python -m etl.probe_ceds --json      # machine-readable
    python -m etl.probe_ceds --record    # refresh the committed record

The ontology is 20 MB of RDF, so it is cached under `data/` like the
workbooks. `data/` is gitignored — this repo ships loaders, not corpora — and
the committed record is what the document is checked against, so no test needs
either the download or the cache.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

from etl.ceds_ontology import (MalformedSource, classes, shapes, unique_labels)

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"
ONTOLOGY = ("https://raw.githubusercontent.com/CEDStandards/CEDS-Ontology/"
            "main/src/CEDS-Ontology.rdf")
LICENCE = "https://api.github.com/repos/CEDStandards/CEDS-Ontology"

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "ceds-ontology.rdf"
RECORD = ROOT / "docs" / "sources" / "ceds-measured.json"


def fetch(url: str, timeout: int = 300) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc


def ontology(use_cache: bool = True) -> str:
    """The RDF, from disk if it is there.

    Written through a `.partial` and renamed, as `probe_pwcs` does. A 20 MB
    download interrupted halfway leaves a file that parses and reports a
    smaller vocabulary, which `classes()` refuses — but only because it
    refuses; the rename is what stops it being written at all.
    """
    if use_cache and CACHE.exists():
        return CACHE.read_text(encoding="utf-8", errors="replace")
    body = fetch(ONTOLOGY)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    partial = CACHE.with_suffix(".partial")
    partial.write_bytes(body)
    partial.replace(CACHE)
    return body.decode("utf-8", errors="replace")


def probe(use_cache: bool = True, quiet: bool = False) -> dict:
    rdf = ontology(use_cache)
    found = classes(rdf)
    counted = unique_labels(found)
    resolved = shapes(found)
    licence = json.loads(fetch(LICENCE, timeout=60))
    result = {
        "retrieved_at": datetime.date.today().isoformat(),
        "source": ONTOLOGY,
        "bytes": len(rdf),
        "licence": (licence.get("license") or {}).get("spdx_id"),
        **counted,
        "shapes": resolved,
    }
    if not quiet:
        print(f"\nCEDS ontology — {ONTOLOGY.rsplit('/', 1)[-1]}\n")
        print(f"  size                     {result['bytes']:>12,} bytes of RDF")
        print(f"  licence                  {result['licence']:>12}")
        print(f"  classes                  {counted['classes']:>12,}")
        print(f"  distinct labels          {counted['distinct_labels']:>12,}"
              f"   — a label identifies a class")
        print("\n  the shapes #33 left provisional\n")
        for ours, one in resolved.items():
            print(f"    {ours:<28} {str(one['ceds_id'] or 'NOT DEFINED'):<10} "
                  f"{one['ceds_label']}")
        print(f"\n  Every identifier is opaque. `Course` is {resolved['Course']['ceds_id']},")
        print("  and the meaning lives in rdfs:label rather than in the URI.")
        print(f"\n  measured {result['retrieved_at']}")
        print("  reproduce with: python -m etl.probe_ceds\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Re-download rather than reading data/.")
    args = parser.parse_args(argv)
    try:
        result = probe(use_cache=not args.no_cache,
                       quiet=args.json or args.record)
    except MalformedSource as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.record:
        RECORD.write_text(json.dumps(result, indent=2) + "\n")
        print(f"wrote docs/sources/{RECORD.name}")
    elif args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
