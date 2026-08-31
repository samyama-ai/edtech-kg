"""What a page in one district's catalogue IS.

Split out of `etl/pwcs_source.py` so that `etl/probe_pwcs.py` can use it. The
probe imports nothing from this package by design — it is the layer everything
else sits on — and `pwcs_source` imports the probe, so the classifier could not
live where it was and be reachable from where it was needed.

That unreachability is exactly what edtech-kg#74 is: the loader classified its
960 pages correctly and the probe called all 960 of them courses, so the two
disagreed about the denominator of every rate the documents quote.

Imports nothing from `etl`. That is the property that makes it importable from
both sides, and it is why the module is this small.
"""

from __future__ import annotations

import re
import urllib.parse

# A pathway lists its courses in a typed field. A page that RENDERS that field
# is a pathway whatever its URL depth says — see `classify`.
#
# **Bound to a class ATTRIBUTE, not to the token anywhere in the document.**
# The unanchored form matched the name inside an HTML comment, in body prose,
# in a `<script>` string and in a reflected `<input value=…>` — measured, all
# four. That was tolerable while it only distinguished "no rows" from "no
# field"; it is not tolerable now that it decides a node's LABEL. It was also
# looser than `COURSE_ROW` in `pwcs_source`, which already requires the token
# inside a real `class="…"` — the classifier was weaker than the row parser it
# gates.
#
# This travelled with the regex from `pwcs_source` when classification moved
# here (#74). It was left behind there, describing a pattern that had gone.
# `\b` was the wrong boundary on BOTH ends. `-` is not a word character, so
# `\b` sits happily between "courses" and a hyphen — a sibling Drupal field
# named `…-section-courses-teaser` matched, and this decides a node's label.
# `(?![\w-])` refuses a longer name; `(?<![\w-])` refuses a longer prefix.
#
# And the attribute was read in ONE of the three forms markup uses. Clean
# Catalog writes double quotes today, so single-quoted or unquoted markup did
# not fail — it fell through to depth, which is the exact classification this
# change exists to stop relying on. A CMS template change would have moved 172
# rows back onto depth silently and every count would still have summed.
PATHWAY_FIELD_PRESENT = re.compile(
    r"""class\s*=\s*(?:"[^"]*|'[^']*|)"""
    r"""(?<![\w-])field--name-field-degree-section-courses(?![\w-])""")

LEVELS = {1: "subject", 2: "course", 3: "pathway"}


def segments(url: str) -> list[str]:
    return [s for s in urllib.parse.urlparse(url).path.strip("/").split("/") if s]


def level(url: str) -> str | None:
    """What the catalogue's URL DEPTH says a page is. `None` for anything else
    — the root, or something nested deeper than a pathway.

    A function so it can be checked directly. It was an `if/elif/else` inside
    `read()`, and the `else` swept every unexpected depth into "pathway",
    where it would be parsed for a course table it does not have.

    **Depth alone is not the classifier — see `classify`.** Four pages publish
    a pathway's course table at course depth, and calling them courses cost
    172 published edges (#87).
    """
    return LEVELS.get(len(segments(url)))


def classify(url: str, markup: str) -> str | None:
    """What a page IS, from what it publishes and then from its depth.

    Depth is the catalogue's own structure and it holds for 956 of 960 pages.
    It does not hold for four, which publish the pathway course-table field at
    COURSE depth — two specialty programmes, International Baccalaureate and
    Virtual Prince William. Classified by depth they loaded as `Course`, their
    course tables were never read, and 172 published rows never became edges
    (#87). Nothing failed: the loader and the engine agreed about a set that
    was already short.

    So the field wins over the depth. A page that renders a course table IS a
    pathway whatever its URL says — the district's own markup is the better
    evidence, and it is the evidence the rows come from.

    Depth still decides everything else, because a subject index and a course
    are not distinguishable by any field either of them carries.

    **The override is unconditional.** A page rendering that field is a
    pathway at ANY depth — a depth-1 index or a depth-4 page would be one too,
    and would appear in `reclassified` rather than in `unclassified`. That is
    the same evidence argument rather than a special case for depth 2, and it
    is stated because "depth decides everything else" reads narrower than the
    code behaves.
    """
    if PATHWAY_FIELD_PRESENT.search(markup):
        return "pathway"
    return level(url)
