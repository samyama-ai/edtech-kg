"""Probe schema.org for the terms this graph would need — the #30 half of #33.

schema.org is the third candidate vocabulary, after CTDL (#28) and before CEDS
(#29), Ed-Fi (#31) and CASE (#32). It matters here for one reason the others do
not share: **its prerequisite property accepts free text as well as a course
reference**, which is the shape the Credential Registry data actually takes.

    python -m etl.probe_schemaorg          # the table
    python -m etl.probe_schemaorg --json   # machine-readable

The vocabulary is published as JSON-LD under CC BY-SA 3.0 at
`schema.org/version/latest/schemaorg-current-https.jsonld` (~1.5 MB). No
third-party dependency, as with the other probes.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

VOCAB = "https://schema.org/version/latest/schemaorg-current-https.jsonld"
USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

# The terms the reuse decision (#33) has to rule on, one per row of its table.
WANTED = [
    "schema:Course",
    "schema:CourseInstance",
    "schema:EducationalOccupationalProgram",
    "schema:EducationalOccupationalCredential",
    "schema:Occupation",
    "schema:EducationalOrganization",
    "schema:CollegeOrUniversity",
    "schema:coursePrerequisites",
    "schema:programPrerequisites",
    "schema:hasCourse",
    "schema:occupationalCategory",
    "schema:educationalCredentialAwarded",
    "schema:competencyRequired",
    "schema:provider",
]


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"unreachable: {url} ({exc})") from exc


def ids(value) -> list[str]:
    """`{"@id": x}`, `[{"@id": x}, …]` and a bare string all flatten the same."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [i.get("@id") if isinstance(i, dict) else i for i in items]


def vocabulary() -> dict:
    payload = get(VOCAB)
    if not payload.lstrip().startswith(b"{"):
        raise ValueError(
            f"{VOCAB} did not return JSON — got {payload[:40]!r}. A 200 carrying an "
            f"error page would otherwise be reported as every term being absent."
        )
    graph = json.loads(payload).get("@graph") or []
    if not graph:
        raise ValueError("the schema.org graph is empty — refusing to report that")

    by_id = {n.get("@id"): n for n in graph if isinstance(n, dict)}
    terms = {}
    for name in WANTED:
        node = by_id.get(name)
        if node is None:
            # An absent term is a real finding for #33 — it means mint or align.
            terms[name] = None
            continue
        terms[name] = {
            "type": node.get("@type"),
            # schema.org uses the same non-committal `…Includes` lists CTDL does.
            "domainIncludes": ids(node.get("schema:domainIncludes")),
            "rangeIncludes": ids(node.get("schema:rangeIncludes")),
            "comment": (node.get("rdfs:comment") or "").strip(),
        }

    prereq = terms.get("schema:coursePrerequisites") or {}
    return {
        "source": VOCAB,
        "terms_in_graph": len(graph),
        "wanted": len(WANTED),
        "present": sum(1 for v in terms.values() if v),
        "absent": [k for k, v in terms.items() if not v],
        "terms": terms,
        # The finding that decides #33's prerequisite row: does the property
        # tolerate the free text that publishers actually write?
        "course_prerequisite_accepts_text": "schema:Text" in prereq.get("rangeIncludes", []),
        "course_prerequisite_accepts_course": "schema:Course" in prereq.get("rangeIncludes", []),
    }


# The definition URLs cited by docs/ontology-reuse.md. #33 requires that a
# reader be able to check every mapping rather than trust it, which only holds
# while the links resolve.
CITED = [
    "https://schema.org/Course",
    "https://schema.org/EducationalOccupationalProgram",
    "https://schema.org/Occupation",
    "https://schema.org/CollegeOrUniversity",
    "https://schema.org/EducationalOccupationalCredential",
    "https://schema.org/coursePrerequisites",
    "https://schema.org/hasCourse",
    "https://schema.org/provider",
    "https://schema.org/educationalCredentialAwarded",
    "https://schema.org/occupationalCategory",
    "https://credreg.net/ctdl/terms/Course",
    "https://credreg.net/ctdl/terms/Occupation",
    "https://credreg.net/ctdl/terms/prerequisite",
    "https://credreg.net/ctdl/terms/isPreparationFor",
    "https://www.imsglobal.org/spec/case/v1p0",
    "https://credreg.net/page/termsofuse",
]


def check_cited(urls: list[str] | None = None) -> dict:
    """Do the cited definition URLs still resolve?

    A reuse decision whose citations rot is a decision nobody can audit. This
    reports every non-200 rather than raising on the first, so one dead link
    does not hide the others.
    """
    results = {}
    for url in (urls if urls is not None else CITED):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT},
                                         method="HEAD")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                results[url] = response.status
        except urllib.error.HTTPError as exc:
            results[url] = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            results[url] = str(exc)
    return {"checked": len(results), "results": results,
            "broken": {u: s for u, s in results.items() if s != 200}}


def probe(quiet: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    v = vocabulary()

    if not quiet:
        print(f"\nschema.org — {v['source']}\n")
        print(f"  terms in the graph {v['terms_in_graph']:>8,}")
        print(f"  wanted for #33     {v['wanted']:>8}    present {v['present']}, "
              f"absent {len(v['absent'])}\n")
        for name, t in v["terms"].items():
            if not t:
                print(f"  {name:44} ABSENT")
                continue
            kind = "class" if t["type"] == "rdfs:Class" else "property"
            print(f"  {name:44} {kind}")
            if t["rangeIncludes"]:
                print(f"      rangeIncludes  {', '.join(t['rangeIncludes'])}")
        print(f"\n  coursePrerequisites accepts a Course reference: "
              f"{v['course_prerequisite_accepts_course']}")
        print(f"  coursePrerequisites accepts free text:          "
              f"{v['course_prerequisite_accepts_text']}")
        print(f"\n  measured {stamp}")
        print("  reproduce with: python -m etl.probe_schemaorg\n")

    return {"retrieved_at": stamp, "vocabulary": v}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true", help="Print the result as JSON.")
    parser.add_argument("--check-urls", action="store_true",
                        help="Verify the definition URLs cited by docs/ontology-reuse.md.")
    args = parser.parse_args(argv)
    if args.check_urls:
        check = check_cited()
        for url, status in check["results"].items():
            print(f"  {status if status == 200 else str(status):<10} {url}")
        print(f"\n  {check['checked']} checked, {len(check['broken'])} broken")
        return 1 if check["broken"] else 0
    try:
        result = probe(quiet=args.json)
    except ValueError as exc:
        print(f"\nrefused: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"\nsource unreachable: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
