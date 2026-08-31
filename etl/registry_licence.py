"""What the Credential Registry's DATA may be used for — edtech-kg#56.

Not the vocabulary. #28 established that CTDL is CC BY 4.0, quoted verbatim,
and that finding is clean. This module exists to stop it travelling one step
too far, because the two questions have different answers and the site puts
them next to each other: credreg.net's footer reads "Policies and Terms of
Use" and then states the CC BY 4.0 licence — of CTDL. A reader who stops there
concludes the Registry is openly licensed. It is not.

Two things are established here, and they are different in kind:

  * `terms_of_use` READS the operator's published terms. A licence position is
    a fact about a document.
  * `carrying_a_rights_field` MEASURES how often a published record says
    anything about its own terms. #56 asks whether per-record licensing is
    even possible; the answer is a count.

Both readers take their input rather than fetching it, so the suite hands them
fixtures and no test reaches the Registry.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

# CTDL's own terms, searched for anything that could carry a per-record licence
# position. `ceterms:License` is NOT one: it is a credential type — a
# government-issued authorisation to do a job, like a nursing licence — and a
# search of the vocabulary for "license" finds it first. `ceterms:copyrightHolder`
# is the only property that names rights in the resource itself.
RIGHTS_FIELDS = ("ceterms:copyrightHolder",)

TERMS_URL = "https://credentialengine.org/terms/"
REGISTRY_FOOTER = "https://credreg.net/"


class MalformedSource(Exception):
    """A page that answered, but not with what it publishes."""


def graph_of(payload: str, what: str) -> list:
    """The `@graph` of a JSON-LD document, or a refusal.

    `json.loads(...)["@graph"]` fails three different ways on a document that
    is not the one asked for — a decode error on an HTML outage page, a
    `TypeError` on a JSON array, a `KeyError` on an object without the key —
    and none of them is `MalformedSource`, so each escaped `main` as a
    traceback instead of `refused:` and exit 3.
    """
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MalformedSource(f"{what} did not parse as JSON ({exc})") from exc
    graph = document.get("@graph") if isinstance(document, dict) else None
    if not isinstance(graph, list):
        raise MalformedSource(
            f"{what} carried no @graph list — the document parsed as "
            f"{type(document).__name__}. That is not the CTDL vocabulary.")
    return graph


def flatten(page: str) -> str:
    """Tags out, entities decoded, whitespace squashed.

    Scripts first, then tags, then entities. Strip the tags first and inline
    JavaScript survives as prose; decode the entities first and one that
    decodes to `<` is eaten as a tag.
    """
    without_code = re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
    return re.sub(r"\s+", " ",
                  html.unescape(re.sub(r"<[^>]+>", " ", without_code))).strip()


def _one(pattern: str, text: str, what: str) -> str:
    found = re.search(pattern, text, re.I)
    if found is None:
        raise MalformedSource(
            f"{TERMS_URL} did not carry {what} ({len(text)} characters of "
            f"text). These sentences ARE the licence position, so their "
            f"absence is not a weaker answer — it means what came back is not "
            f"this page. Refusing rather than recording a blank, because a "
            f"blank here reads as 'no restriction found'.")
    return re.sub(r"\s+", " ", found.group(1)).strip()


def terms_of_use(page: str) -> dict:
    """The three sentences that decide whether this repo may load the Registry.

    Quoted, not summarised. Each is the operator's own wording, and the
    conclusion rests on them rather than on a reading of them.
    """
    text = flatten(page)
    return {
        "source": TERMS_URL,
        "grant": _one(
            r"(Credential Engine grants you a personal, limited, revocable, "
            r"nonexclusive, and nontransferable license.{0,200}?internal use "
            r"within your organization)", text, "the licence grant"),
        "restriction": _one(
            r"(You may not reproduce, publish, distribute, display, modify, "
            r"create derivative works from.{0,200}?prior consent of Credential "
            r"Engine)", text, "the redistribution restriction"),
        "developer_agreement": _one(
            r"((?:develop software applications that access and use data|"
            r"aggregate, publish, transmit).{0,400}?Developer Agreement)",
            text, "the Developer Agreement requirement"),
        "read_or_measured": "read",
    }


def rights_terms_in(vocabulary: list[dict]) -> list[str]:
    """Every CTDL term that could carry a rights position, prefix stripped.

    "terms" is IN the pattern, and it is the reason the prefix has to go
    first. A property named `termsOfUse` is exactly what #56 asks whether CTDL
    has, so the word cannot be dropped from the search — and every term in the
    vocabulary is named `ceterms:something`, so searching the raw identifiers
    matches all 1,032 of them. That is how a first pass reported a vocabulary
    full of licensing properties. Four have a rights-shaped local name and
    none is named for terms of use.
    """
    found = []
    for term in vocabulary:
        name = str(term.get("@id", "")).split(":", 1)[-1]
        if re.search(r"licen[cs]|copyright|rights|terms", name, re.I):
            found.append(term["@id"])
    if not found:
        raise MalformedSource(
            "no rights-shaped term found in the CTDL vocabulary at all — "
            "`ceterms:copyrightHolder` is published, so zero means the "
            "vocabulary did not load rather than that it has none.")
    return sorted(found)


def carrying_a_rights_field(envelopes: list[dict]) -> dict:
    """How many published records say anything about their own terms.

    #56 asks whether individual envelopes carry a licence field and how often
    it is populated. The count is over the DECODED resource graph, not the
    envelope wrapper — the wrapper is registry bookkeeping and carries no
    field of this kind on any record.
    """
    carrying = 0
    for envelope in envelopes:
        # One guard, not two: `.get("decoded_resource", {})` still returns
        # None when the key is present and null, so the default is not the
        # protection — the type check is. A non-list @graph iterates its KEYS,
        # which would turn `field in node` into a substring test against a
        # string and report a rights field that is not there.
        resource = envelope.get("decoded_resource")
        graph = (resource.get("@graph") or []) if isinstance(resource, dict) else []
        if any(field in node for node in graph
               if isinstance(node, dict) for field in RIGHTS_FIELDS):
            carrying += 1
    return {"envelopes": len(envelopes), "carrying_a_rights_field": carrying,
            "fields_looked_for": list(RIGHTS_FIELDS), "read_or_measured": "measured"}


# --------------------------------------------------------------------------
# fetching, and the committed record the document is checked against
# --------------------------------------------------------------------------

USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"
VOCABULARY = "https://credreg.net/ctdl/schema/encoding/json"
RECORD = pathlib.Path(__file__).resolve().parents[1] / "docs" / "sources" / \
    "registry-licence-measured.json"
SAMPLE_PER_PAGE, SAMPLE_PAGES = 25, 3


def page_text(url: str, timeout: int = 60) -> str:
    """One page, or a refusal naming it.

    `timeout` is a parameter because the CTDL vocabulary is a 1,032-term JSON
    document served slowly enough to exceed a minute on an ordinary run.
    Refusing on that would report "the vocabulary carries no rights term",
    which is the false zero this module exists to avoid.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc


def probe(quiet: bool = False) -> dict:
    """Read the terms, and count what the records say about their own.

    Imported here rather than at module scope: `registry_read` is the fetching
    layer and this module's readers must stay importable without it, so that
    the tests can exercise them with no network reachable at all.
    """
    from etl.registry_read import REGISTRY, HttpStatus, get, parse
    from etl.registry_read import MalformedSource as ReadRefused

    terms = terms_of_use(page_text(TERMS_URL))
    vocabulary = graph_of(page_text(VOCABULARY, timeout=180),
                          "the CTDL vocabulary")
    envelopes: list[dict] = []
    for kind in ("course", "credential", "learning_opportunity_profile", "pathway"):
        for page in range(1, SAMPLE_PAGES + 1):
            what = f"page {page} of the {kind} search"
            # `registry_read` raises its OWN exception classes, and its
            # `MalformedSource` is a different class from this module's. A 503
            # from the Registry, or a non-JSON search page, therefore escaped
            # `main`'s `except MalformedSource` as a traceback — the one thing
            # `page_text` is careful to prevent for the pages it fetches
            # itself. The borrowed layer is put on the same channel here.
            try:
                body = parse(get(f"{REGISTRY}/ce-registry/{kind}/search"
                                 f"?page={page}&per_page={SAMPLE_PER_PAGE}"),
                             what)
            except (HttpStatus, ReadRefused) as exc:
                raise MalformedSource(f"{what}: {exc}") from exc
            # Mirrors `etl/probe_registry.py`, which checks this because the
            # Registry has returned other shapes. Without it an error body
            # that is a JSON object extends `envelopes` with its KEYS, and
            # `carrying_a_rights_field` then calls `.get` on a `str`.
            if not isinstance(body, list):
                raise MalformedSource(
                    f"{what} returned {type(body).__name__}, not a list of "
                    f"envelopes")
            envelopes += [e for e in body if isinstance(e, dict)]

    result = {"retrieved_at": datetime.date.today().isoformat(),
              "terms_of_use": terms,
              "rights_terms_in_ctdl": rights_terms_in(vocabulary),
              "records": carrying_a_rights_field(envelopes)}
    if not quiet:
        print("\nCredential Registry — the DATA, not the vocabulary\n")
        print(f"  grant        {terms['grant']}")
        print(f"  restriction  {terms['restriction']}")
        print(f"  developers   {terms['developer_agreement'][:120]}…")
        print(f"\n  rights-shaped CTDL terms  "
              f"{', '.join(result['rights_terms_in_ctdl'])}")
        print(f"  — of those, one names rights in the resource: "
              f"{RIGHTS_FIELDS[0]}")
        print("    ceterms:License is a CREDENTIAL type, not a data licence")
        print(f"\n  records inspected         {result['records']['envelopes']:>6,}")
        print(f"  saying anything about their own terms "
              f"{result['records']['carrying_a_rights_field']:>6,}")
        print(f"\n  read {result['retrieved_at']}")
        print("  reproduce with: python -m etl.registry_licence\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json or args.record)
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
