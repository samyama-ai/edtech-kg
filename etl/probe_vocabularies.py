"""Measure Ed-Fi and CASE — edtech-kg#31 and #32.

    python -m etl.probe_vocabularies             # the tables
    python -m etl.probe_vocabularies --json      # machine-readable
    python -m etl.probe_vocabularies --record    # refresh the committed record

The Ed-Fi specification is 3.7 MB and is cached under `data/`, which is
gitignored. The CASE context and specification page are small and are not
cached: the CASE licence is a licence position, and those are re-read rather
than served from a copy taken months ago.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import urllib.error
import urllib.request

from etl.vocabularies import (MalformedSource, case_licence, case_terms,
                              edfi_resources, json_object)

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"
EDFI_SPEC = ("https://raw.githubusercontent.com/Ed-Fi-Alliance-OSS/"
             "Ed-Fi-API-Specifications/main/api-specifications/resources/"
             "resources-ds-6.0.yaml")
EDFI_REPO = "https://api.github.com/repos/Ed-Fi-Alliance-OSS/Ed-Fi-API-Specifications"
CASE_CONTEXT = ("https://purl.imsglobal.org/spec/case/v1p0/context/"
                "imscasev1p0_context_v1p0.jsonld")
CASE_SPEC = "https://www.imsglobal.org/spec/case/v1p0"

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "edfi-resources-ds-6.0.yaml"
RECORD = ROOT / "docs" / "sources" / "vocabularies-measured.json"


def fetch(url: str, timeout: int = 180) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc


def specification(use_cache: bool = True) -> str:
    if use_cache and CACHE.exists():
        return CACHE.read_text(encoding="utf-8", errors="replace")
    body = fetch(EDFI_SPEC)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    partial = CACHE.with_suffix(".partial")
    partial.write_bytes(body)
    partial.replace(CACHE)
    return body.decode("utf-8", errors="replace")


def probe(use_cache: bool = True, quiet: bool = False) -> dict:
    edfi = edfi_resources(specification(use_cache))
    # GitHub reports `spdx_id: null` for a licence it does not recognise, and
    # omits the object entirely on some responses. Both are "it did not say",
    # not a crash, and neither is the same thing as "there is no licence".
    metadata = json_object(fetch(EDFI_REPO, timeout=60),
                           "the Ed-Fi repository metadata")
    licence = metadata.get("license")
    edfi["licence"] = (licence.get("spdx_id") if isinstance(licence, dict)
                       else None)
    case = case_terms(fetch(CASE_CONTEXT, timeout=60).decode("utf-8", "replace"))
    case["licence"] = case_licence(fetch(CASE_SPEC, timeout=60)
                                   .decode("utf-8", "replace"))
    result = {"retrieved_at": datetime.date.today().isoformat(),
              "ed_fi": {"source": EDFI_SPEC, **edfi},
              "case": {"source": CASE_CONTEXT, **case}}
    if not quiet:
        print("\nEd-Fi Data Standard 6.0 — an API shape, not a vocabulary\n")
        print(f"  licence                  "
              f"{edfi['licence'] or 'unreported':>14}")
        print(f"  component schemas        {edfi['schemas']:>14,}")
        print(f"  of those, edFi_          {edfi['edfi_schemas']:>14,}")
        print(f"  REST resource paths      {edfi['resource_paths']:>14,}")
        print(f"  citable term URIs        {str(edfi['term_uris']):>14}"
              f"   <- there are none")
        for ours, theirs in edfi["shapes"].items():
            print(f"    {ours:<26} {theirs or 'NOT DEFINED'}")

        print("\nCASE v1p0 — a vocabulary, with a licence to read\n")
        print(f"  terms in the JSON-LD context   {case['terms']:>8,}")
        print(f"  of those, datatype entries     {case['datatype_entries']:>8,}")
        for ours, theirs in case["shapes"].items():
            print(f"    {ours:<26} {theirs or 'NOT DEFINED'}")
        print(f"\n  licence  {case['licence']['governs_product_use']}")
        print("           ^ neither Apache-2.0 nor CC — unlike CEDS and Ed-Fi")
        print(f"\n  measured {result['retrieved_at']}")
        print("  reproduce with: python -m etl.probe_vocabularies\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Re-download the Ed-Fi specification.")
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
