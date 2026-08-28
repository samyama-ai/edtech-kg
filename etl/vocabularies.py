"""Ed-Fi and CASE — the two investigations #69 is still waiting on.

edtech-kg#31 and #32, together, because the answer either one produces is only
useful next to the other and next to CEDS ([`probe_ceds`](probe_ceds.py)).
#33's four provisional rows are decided by a comparison, not by three verdicts
filed separately.

They are different KINDS of thing, and that is most of the finding:

  * **Ed-Fi is an API shape.** `edFi_school` is a schema name inside an
    OpenAPI document, not a resolvable identifier. There is nothing to cite —
    which is exactly what #31's title already says, now measured.
  * **CASE is a vocabulary with resolvable terms**, published as JSON-LD at a
    purl, and its spec routes product use through a licence with 1EdTech.

Both readers take their document text. Neither fetches, so no test downloads
the 3.7 MB specification.
"""

from __future__ import annotations

import json
import re

# `    name:` at exactly four spaces — an OpenAPI component schema. Anchored to
# the indentation rather than searched for anywhere, because the same names
# recur throughout the document as `$ref` targets and as property names, and
# counting those reports several thousand schemas that do not exist.
COMPONENT_SCHEMA = re.compile(r"^    ([A-Za-z][A-Za-z0-9_]*):$", re.M)
RESOURCE_PATH = re.compile(r"^  (/ed-fi/[a-zA-Z]+):$", re.M)

# The shapes #33 left provisional, as each vocabulary names them.
EDFI_SHAPES = {"School": "edFi_school",
               "District": "edFi_localEducationAgency",
               "Course": "edFi_course",
               "Standard / competency": "edFi_learningStandard"}
CASE_SHAPES = {"Standard / competency": "CFItem",
               "Standard set": "CFDocument",
               "Course ALIGNS_TO Standard": "CFAssociation"}


class MalformedSource(Exception):
    """A document that parsed, but is not the specification."""


def edfi_resources(spec: str) -> dict:
    """What Data Standard 6.0 declares, counted off the OpenAPI document.

    Refuses on a small count for the reason `ceds_ontology` does: a truncated
    or substituted document yields a number rather than an error, and the
    number is what the page argues from.
    """
    schemas = COMPONENT_SCHEMA.findall(spec)
    resources = sorted(set(RESOURCE_PATH.findall(spec)))
    owned = sorted({s for s in schemas if s.startswith("edFi_")})
    if len(owned) < 200 or not resources:
        raise MalformedSource(
            f"only {len(owned)} edFi_ schemas and {len(resources)} resource "
            f"paths found in {len(spec):,} characters. Data Standard 6.0 "
            f"declares hundreds of each, so this is a truncated or "
            f"substituted document rather than a smaller standard.")
    return {"schemas": len(set(schemas)), "edfi_schemas": len(owned),
            "resource_paths": len(resources),
            "shapes": {ours: (theirs if theirs in owned else None)
                       for ours, theirs in EDFI_SHAPES.items()},
            # No URI. That is the finding, and recording `None` rather than
            # omitting the key is what makes it visible in the record.
            "term_uris": None}


def case_terms(context: str) -> dict:
    """The CASE JSON-LD context, and whether it names the shapes we need.

    `dt`-prefixed entries are datatype declarations rather than classes —
    `dtCFItem` sits beside `CFItem` — and counting both doubles the
    vocabulary. The shapes are looked up by exact name for that reason.
    """
    terms = json.loads(context).get("@context", {})
    if not isinstance(terms, dict) or len(terms) < 50:
        raise MalformedSource(
            f"the CASE context carried {len(terms) if hasattr(terms, '__len__') else 0} "
            f"terms. The published v1p0 context carries over a hundred, so "
            f"this is not that document.")
    return {"terms": len(terms),
            "shapes": {ours: (theirs if theirs in terms else None)
                       for ours, theirs in CASE_SHAPES.items()},
            "datatype_entries": sum(1 for t in terms if t.startswith("dt"))}


def case_licence(page: str) -> dict:
    """1EdTech's own sentence about using the specification.

    Quoted rather than summarised. It is the sentence that separates CASE from
    CEDS and Ed-Fi, which are both Apache-2.0 and need no such reading.
    """
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ",
                                      re.sub(r"(?is)<(script|style).*?</\1>", " ", page)))
    found = re.search(r"(Use of this specification to develop products or "
                      r"services is governed by the license with 1EdTech[^.]*)", flat)
    if found is None:
        raise MalformedSource(
            "the CASE specification page did not carry its licence sentence. "
            "Refusing rather than recording a blank, because a blank here "
            "reads as 'no restriction found' — and this is the one of the "
            "three vocabularies that has one.")
    return {"governs_product_use": re.sub(r"\s+", " ", found.group(1)).strip(),
            "spdx": None}
