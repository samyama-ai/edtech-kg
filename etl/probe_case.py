"""Are academic standards reachable as data? Measured on three routes.

    python -m etl.probe_case --record

edtech-kg#32. Course titles do not survive crossing a district boundary;
standards might. 1EdTech's **CASE** is the specification for exchanging
learning standards in machine-readable form, and **CASE Network 2** is
advertised as hosting frameworks from all 50 US states, "free to browse and
use".

The issue is explicit that this has to be measured rather than believed:
*"'available for anyone to use' on a website is a statement of intent, not a
licence — find the licence."* It also names the edge that would make standards
worth having: a state publishing a **course → standard** alignment, with
Florida's CPALMS as the first place to look.

Three routes, each answering a different question:

  * **CASE Network 2** — is the advertised registry reachable as an API?
  * **OpenSALT** — the reference CASE implementation answers. What is in it?
  * **CPALMS** — does a state's course page carry its standards in the served
    markup, or only in a browser?

A tier serving none of the 26 questions in `docs/questions.md` stays out. That
is the rule that file set, and this measures whether standards clear it.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import hashlib
import re
import sys
import urllib.error
import urllib.request

from etl.identity import USER_AGENT
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "standards" / "case-measured.json"
RECORD_NOTE = ("Measured by `python -m etl.probe_case --record`. Each route "
               "records the status it answered with, so a 403 is a measured "
               "refusal and not an absence.")

CASE_NETWORK = "https://casenetwork.imsglobal.org"
OPENSALT = "https://opensalt.net"
#: Several course pages, not one. "Florida publishes no alignment in its
#: markup" was a claim about a single URL — one extra request each makes it a
#: claim about CPALMS. Ids are spread across the catalogue rather than
#: consecutive, so a run of pages from one subject cannot stand in for it.
CPALMS_COURSES = (
    "https://www.cpalms.org/PreviewCourse/Preview/13087",
    "https://www.cpalms.org/PreviewCourse/Preview/17414",
    "https://www.cpalms.org/PreviewCourse/Preview/20205",
)

#: The paths a CASE server must serve. From the specification, so a server
#: answering none of them is not a CASE endpoint whatever it is called.
CASE_PATHS = ("/ims/case/v1p0/CFDocuments", "/uri/", "/CFDocuments")

#: A Florida standard code, in the shapes CPALMS publishes. Searched in the
#: SERVED markup — the question is whether the alignment is in the document or
#: only in a browser that ran its JavaScript.
FLORIDA_CODE = re.compile(
    r"\b(MA\.\d+\.[A-Z]+\.\d+\.\w+|LAFS\.\d+\.\w+\.\d+\.\d+"
    r"|SC\.\d+\.[A-Z]\.\d+\.\d+|ELA\.\d+\.\w+\.\d+\.\d+)\b")


class Unreachable(RuntimeError):
    """A host did not answer at all. Distinct from answering with a refusal."""


def fetch(url: str) -> tuple[int | str, str]:
    """The STATUS and the body — a refusal is a measurement, not an error.

    A 403 on a registry advertised as "free to browse and use" is the finding,
    so it has to come back as data rather than as an exception the caller
    turns into a shrug.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as refused:
        return refused.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


def case_network() -> dict:
    """Is the advertised registry a CASE API, or a browser application?

    Each documented CASE path is asked for, and what came back is recorded.
    A host returning the same HTML shell for every path is a single-page
    application — the standards are behind JavaScript, and "machine-readable"
    describes the format rather than the access.
    """
    root_status, root = fetch(f"{CASE_NETWORK}/")
    paths = {}
    for path in CASE_PATHS:
        status, body = fetch(f"{CASE_NETWORK}{path}")
        paths[path] = {
            "status": status,
            "bytes": len(body),
            "is_json": _is_json(body),
            # The tell: a path answering 200 with the ROOT's markup is the
            # app's own catch-all, not an endpoint.
            "same_as_root": bool(body) and body == root,
        }
    served = [p for p, f in paths.items() if f["is_json"]]
    return {
        "base": CASE_NETWORK,
        "root_status": root_status,
        "root_bytes": len(root),
        "paths": paths,
        "serves_case_json": served,
        "reachable_as_data": bool(served),
    }


def _is_json(body: str) -> bool:
    if not body.strip():
        return False
    try:
        json.loads(body)
        return True
    except json.JSONDecodeError:
        return False


def opensalt() -> dict:
    """The reference CASE implementation answers. What is actually in it?

    The issue's claim is fifty states for two subjects. This counts what the
    server publishes and who authored it, because a CASE API that works and
    holds test fixtures is not the same finding as one that holds a state's
    standards.
    """
    status, body = fetch(f"{OPENSALT}/ims/case/v1p0/CFDocuments")
    if not _is_json(body):
        return {"base": OPENSALT, "status": status, "documents": 0,
                "note": "the reference implementation did not return CASE JSON"}
    docs = json.loads(body).get("CFDocuments") or []
    creators = collections.Counter(d.get("creator") for d in docs)
    return {
        "base": OPENSALT,
        "status": status,
        "documents": len(docs),
        "distinct_creators": len(creators),
        "top_creators": creators.most_common(10),
        # Recorded because it decides whether these are state standards. A
        # creator naming a vendor or a test is not a state education agency.
        "documents_with_a_subject": sum(1 for d in docs if d.get("subject")),
        **licence_fields(docs),
    }


#: How the CASE v1p0 `CFDocument` model spells it. **American, and it was
#: written here as `licenceUri`** — so the count was a property of the key
#: name rather than of the server, and returned 0 whatever OpenSALT published.
#: It underwrote the page's claim that the licence question cannot be answered
#: from the data.
#:
#: A `LinkURI` is an object rather than a bare string, so truthiness is the
#: test — a populated one is a non-empty dict.
LICENCE_FIELDS = ("licenseUri", "licenceUri", "rights", "rightsHolder")


def licence_fields(docs: list[dict]) -> dict:
    """What the documents say about licensing, and every key they carry.

    **The key set is recorded, not just the counts.** A count of a key that
    does not exist is zero however the server behaves, and the test could not
    catch it because the fixture fed the same misspelling — the code agreeing
    with itself. Recording what the documents ACTUALLY carry makes a zero
    checkable and a future field rename visible rather than silent.
    """
    keys: dict[str, int] = {}
    for doc in docs:
        for key in doc:
            keys[key] = keys.get(key, 0) + 1
    return {
        "documents_by_licence_field": {
            field: sum(1 for d in docs if d.get(field))
            for field in LICENCE_FIELDS},
        # Every key any document carries, with how many carry it. This is the
        # evidence behind "no licence field is published at all".
        "keys_observed": dict(sorted(keys.items(), key=lambda kv: -kv[1])),
    }


def cpalms() -> dict:
    """Do Florida's course pages carry their standards in the served markup?

    The edge the issue calls the one that "makes this useful rather than
    merely present". Measured on the DOCUMENT the server sends — an alignment
    a browser assembles is not an alignment anything else can read.
    """
    pages, digests = [], {}
    for url in CPALMS_COURSES:
        status, body = fetch(url)
        course_id = url.rsplit("/", 1)[-1]
        digests[course_id] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        pages.append({
            "url": url,
            "course_id": course_id,
            "status": status,
            "bytes": len(body),
            "standard_links": len(set(re.findall(
                r"PreviewStandard/Preview/(\d+)", body))),
            "standard_codes": len(set(FLORIDA_CODE.findall(body))),
            # **Does the page mention the course it is for?** Three ids
            # returning identical bytes is only conclusive if none of them
            # carries its own identifier — otherwise a coincidence of length
            # could look like a shell.
            "names_its_own_course_id": course_id in body,
        })
    answered = [p for p in pages if p["status"] == 200]
    distinct = len(set(digests.values()))
    return {
        "pages": pages,
        "answered": len(answered),
        # Totals across the pages that answered. A page that did not load is
        # not a page publishing no alignment.
        "standard_links": sum(p["standard_links"] for p in answered),
        "standard_codes": sum(p["standard_codes"] for p in answered),
        "distinct_documents": distinct,
        # The finding this measurement turned out to carry. If three
        # different course ids return ONE document, the server is not
        # publishing courses at all — the whole page is assembled in a
        # browser, and the missing alignment is a consequence rather than a
        # separate fact.
        "serves_one_document_for_every_course": distinct == 1 and len(answered) > 1,
        "sha256_by_course_id": digests,
    }


def measure() -> dict:
    return {
        "_": RECORD_NOTE,
        "retrieved_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%d"),
        "case_network": case_network(),
        "opensalt": opensalt(),
        "cpalms": cpalms(),
    }


def report(measured: dict) -> None:
    net = measured["case_network"]
    print(f"  CASE Network 2 ({net['base']})")
    print(f"    root {net['root_status']}, {net['root_bytes']} bytes")
    for path, found in net["paths"].items():
        same = "  (the root's own markup)" if found["same_as_root"] else ""
        print(f"    {str(found['status']):<5} {path:<34} "
              f"json={found['is_json']}{same}")
    print(f"    reachable as data: {net['reachable_as_data']}\n")

    salt = measured["opensalt"]
    print(f"  OpenSALT ({salt['base']})  status {salt['status']}")
    print(f"    {salt.get('documents', 0)} documents from "
          f"{salt.get('distinct_creators', 0)} creators, "
          f"{salt.get('documents_with_a_licence_uri', 0)} with a licence URI")
    for creator, n in (salt.get("top_creators") or [])[:5]:
        print(f"      {n:>3}  {creator}")

    fl = measured["cpalms"]
    print(f"\n  CPALMS  {fl['answered']} of {len(fl['pages'])} pages answered")
    for page in fl["pages"]:
        print(f"    {str(page['status']):<5} {page['bytes']:>7} bytes  "
              f"links={page['standard_links']}  codes={page['standard_codes']}  "
              f"names_own_id={page['names_its_own_course_id']}  "
              f"{page['course_id']}")
    print(f"    across the answered pages: {fl['standard_links']} links, "
          f"{fl['standard_codes']} codes")
    print(f"    distinct documents for {len(fl['pages'])} course ids: "
          f"{fl['distinct_documents']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etl.probe_case")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.json and args.record:
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2

    try:
        measured = measure()
    except Unreachable as gone:
        print(f"unreachable: {gone}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0
    report(measured)
    if args.record:
        # REFUSED when no route produced a status. Unreachable is raised
        # before this today — `fetch` propagates it and `main` returns 1 —
        # so this cannot fire on the current code. It is kept deliberately:
        # `fetch` returns a status rather than raising for every case that
        # matters here, and the day a non-raising failure path is added, a
        # record of nothing must not overwrite a record of something.
        if not any(measured[route].get("status") or
                   measured[route].get("root_status")
                   for route in ("case_network", "opensalt", "cpalms")):
            print("refusing to --record: no route answered at all.",
                  file=sys.stderr)
            return 3
        write_record(RECORD, measured)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
