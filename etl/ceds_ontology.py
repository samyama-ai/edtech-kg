"""Reading the CEDS ontology — edtech-kg#29.

CEDS is the federal vocabulary this sector already speaks, and #33's reuse
decision left four rows provisional pending it. The three questions #69 sets
are the ones answered here, and only the first two are about CEDS itself:

  1. **Does it define the term?** Measured off the ontology, not read off a
     web page.
  2. **Is it usable?** Apache-2.0, and published as RDF rather than described
     in a PDF — which is the distinction that decides whether "align to CEDS"
     is a citation or a transcription job.
  3. **Do publishers use it?** Not answerable here and deliberately not
     guessed at: CEDS is a reporting vocabulary rather than a publishing one,
     so "used" means something different from what it meant for CTDL (#53).

**Every class is named by an opaque identifier** — `C200072`, not `Course`.
The meaning is in `rdfs:label`. That is the finding that costs something: a
graph aligning to CEDS cites `w3id.org/CEDStandards/terms/C200072` and carries
the label separately, where CTDL and schema.org put the meaning in the URI.

`classes()` takes the RDF text rather than fetching it, so the suite hands it
a fixture and no test downloads 20 MB.
"""

from __future__ import annotations

import re

# Both are used in this document and both carry CEDS classes: `owl:Class` for
# most, `rdfs:Class` for 404 of them. Reading one gives 965 of 1,369 and no
# sign that the rest exist — the shape of undercount that reads as a finding.
CLASS_BLOCK = re.compile(
    r'<(owl:Class|rdfs:Class) rdf:about="https://w3id\.org/CEDStandards/terms/'
    r'([^"]+)"(.*?)</\1>', re.S)
LABEL = re.compile(r"<rdfs:label>([^<]*)</rdfs:label>")

NAMESPACE = "https://w3id.org/CEDStandards/terms/"

# The four shapes #33 left provisional, as CEDS labels them. Written as the
# LABEL rather than the identifier: an identifier here would be a number
# nobody could check against the source, and the point of this module is that
# the identifier is not the name.
SHAPES = {
    "School": "K12 School",
    "District": "Local Education Agency",
    "Course": "Course",
    "Standard / competency": "Competency Definition",
    "Course ALIGNS_TO Standard": "Competency Definition Association",
}


class MalformedSource(Exception):
    """RDF that parsed, but is not the ontology."""


def classes(rdf: str) -> dict[str, str]:
    """Every CEDS-owned class, as `{identifier: label}`.

    Refuses rather than returning what it found. A truncated download, a
    rate-limit page or an HTML error saved as `.rdf` all yield a small number
    of matches rather than zero, and a small number here would be published as
    "CEDS defines fewer terms than expected".
    """
    found = {}
    for _, identifier, body in CLASS_BLOCK.findall(rdf):
        labels = LABEL.findall(body)
        if labels:
            found[identifier] = labels[0].strip()
    if len(found) < 500:
        raise MalformedSource(
            f"only {len(found)} labelled CEDS classes found in "
            f"{len(rdf):,} characters. The published ontology carries over a "
            f"thousand, so this is a truncated or substituted document rather "
            f"than a smaller vocabulary. Refusing, because the number this "
            f"would report is the number the page argues from.")
    return found


def unique_labels(found: dict[str, str]) -> dict[str, int]:
    """Whether a label identifies a class on its own.

    It does, and that is worth measuring rather than assuming: if labels
    collided, citing CEDS by label would be ambiguous and the only safe
    citation would be the opaque identifier. Reported as two numbers so the
    page cannot claim uniqueness without them agreeing.
    """
    return {"classes": len(found), "distinct_labels": len(set(found.values()))}


def shapes(found: dict[str, str], wanted: dict[str, str] = SHAPES) -> dict:
    """Each shape #33 left provisional, resolved to a CEDS identifier.

    A shape CEDS does not define comes back `None` rather than being dropped.
    An absent key and a key with no match read identically to a caller, and
    "CEDS has no term for this" is the answer that decides `mint` over
    `align`.
    """
    by_label = {label: identifier for identifier, label in found.items()}
    return {ours: {"ceds_label": theirs,
                   "ceds_id": by_label.get(theirs),
                   "uri": NAMESPACE + by_label[theirs] if theirs in by_label else None}
            for ours, theirs in wanted.items()}
