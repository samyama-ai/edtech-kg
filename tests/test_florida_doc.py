"""The Florida verdict, held to the record it rests on.

#55's answer is "zero courses", quoted in prose in `docs/sources/florida-registry.md`.
The probe and its record landed in the preceding commit; this is what stops the
prose drifting from them — the repo's most common review finding, one figure
written in several places and changed in one.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "florida-registry-measured.json").read_text("utf-8"))


# --- the prose against the record -------------------------------------------

DOC = "docs/sources/florida-registry.md"

#: `(expected value, pattern capturing the figure out of its sentence)`.
#: Anchored on wording, so a reword fails loudly rather than matching some
#: other number further down the page.
QUOTED = [
    (RECORD["records"], r"which is the whole-community total"),
    (RECORD["by_type"]["credential"], r"\| `credential` \| \*\*([\d,]+)\*\* \|"),
    (RECORD["by_type"]["organization"], r"\| `organization` \| ([\d,]+) \|"),
    (RECORD["profile"]["sampled"], r"Sampled ([\d,]+) across"),
    (RECORD["profile"]["of_pages"], r"across \d+ of ([\d,]+) pages"),
    (RECORD["profile"]["field_coverage"]["ceterms:occupationType"],
     r"`ceterms:occupationType` \| ([\d,]+) \|"),
]


@pytest.mark.parametrize("expected, pattern", QUOTED,
                         ids=[str(e) for e, _ in QUOTED])
def test_a_figure_the_doc_quotes_is_the_one_measured(expected, pattern):
    text = (ROOT / DOC).read_text(encoding="utf-8")
    found = re.search(pattern, text)
    assert found, f"{DOC} no longer states this — {pattern!r} matched nothing"
    if not found.groups():
        return              # presence-only anchor, checked below
    said = int(found.group(1).replace(",", ""))
    assert said == expected, (
        f"{DOC} says {said}; the record measured {expected}.\n"
        f"  sentence: {found.group(0)}\n"
        f"Re-run `python -m etl.probe_florida --record`, then update the prose.")


def test_the_sum_the_doc_prints_actually_sums():
    """Reviewers add these up, and this repo has shipped a table that did not.
    The doc prints `10,241 + 336 + 1 = 10,578` as prose."""
    text = (ROOT / DOC).read_text(encoding="utf-8")
    found = re.search(r"([\d,]+) \+ ([\d,]+) \+ ([\d,]+) = ([\d,]+)", text)
    assert found, "the doc no longer shows the reconciliation"
    parts = [int(g.replace(",", "")) for g in found.groups()]
    assert sum(parts[:3]) == parts[3] == RECORD["records"], found.group(0)


def test_the_doc_does_not_quote_a_share_as_if_it_were_the_community():
    """The census/sample line, which is the whole strength of this finding.

    Every coverage figure is a share of 400 sampled credentials, not of 10,241.
    The doc must keep saying so where it says the numbers.
    """
    text = (ROOT / DOC).read_text(encoding="utf-8")
    assert "This part is a sample" in text
    assert "a census, not a sample" in text

