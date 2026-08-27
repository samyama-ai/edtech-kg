"""Every file a document points at must exist in this tree.

Written after a dangling citation blocked three separate pull requests — #51
cited `docs/scope.md` before it was merged, #63 and #65 both cited
`docs/ontology-reuse.md`, which lives on a different branch. Each time a human
reviewer found it, which is three reviews spent on the same class of error.

The failure is specific to how this repo works: documents cite each other, and
branches are stacked, so a citation that resolves on the author's machine can be
dangling in the branch the reviewer reads.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted(ROOT.glob("docs/**/*.md")) + sorted(ROOT.glob("*.md"))

# `[text](path)` and bare `path` in backticks, skipping URLs and anchors.
LINK = re.compile(r"\[[^\]]*\]\((?!https?:|#)([^)#]+)")
BACKTICK = re.compile(r"`((?:docs/|etl/|schema/|tests/)[\w\-./]+\.\w+)`")


def references(document: Path):
    # `encoding="utf-8"`, not `errors="replace"`. These are repo-controlled
    # Markdown files, so the encoding is known — and `read_text()` with no
    # encoding uses the locale's, which decodes them wrongly on a non-UTF-8
    # machine. `errors="replace"` stops the crash and substitutes U+FFFD, so a
    # path with a non-ASCII character then either fails to match the pattern
    # (a false pass) or resolves to a name that is not there (a confusing false
    # failure). Naming the encoding fixes the cause rather than the symptom.
    text = document.read_text(encoding="utf-8")
    for match in LINK.finditer(text):
        yield match.group(1).strip(), "link"
    for match in BACKTICK.finditer(text):
        yield match.group(1).strip(), "backtick"


@pytest.mark.parametrize("document", DOCS, ids=lambda d: str(d.relative_to(ROOT)))
def test_every_file_a_document_cites_exists(document):
    missing = []
    for reference, kind in references(document):
        # A link is relative to the citing document; a backticked path is
        # written from the repo root, which is how this repo uses them.
        candidates = [document.parent / reference, ROOT / reference]
        if not any(candidate.exists() for candidate in candidates):
            missing.append(f"{reference} ({kind})")
    assert not missing, (
        f"{document.relative_to(ROOT)} cites files that are not in this tree: "
        f"{missing}. If they arrive with another branch, name them in prose "
        f"instead of linking, and say which branch."
    )


def test_the_check_covers_the_documents_that_exist():
    """Guards against the glob quietly matching nothing."""
    assert len(DOCS) >= 5, [str(d) for d in DOCS]


def test_every_probe_the_readme_names_exists():
    """The README named `etl/probe_bls.py`, which lives on an unmerged branch.

    A front page that points at a file the repo does not contain is the worst
    place for that error to be, and reading the table cannot catch it — the row
    was accurate, just not yet true here.
    """
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(errors="replace")
    named = set(re.findall(r"`(probe_\w+)`", readme))
    assert named, "the README names no probes — did the sources table move?"
    missing = sorted(n for n in named if not (root / "etl" / f"{n}.py").exists())
    assert not missing, f"named in README.md but not in etl/: {missing}"


def test_the_readme_source_count_matches_its_table():
    """"seven measured public sources" and a table with a different number of
    rows is the hand-counted-figure class, on the front page."""
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(errors="replace")
    stated = re.search(r"plus (\w+) measured public sources", readme)
    assert stated, "the README no longer states a source count in that shape"
    rows = len(re.findall(r"^\| [^|]+ \| `probe_\w+` \|", readme, re.M))
    from tests.spelling import spelled
    assert spelled(stated.group(1)) == rows, (
        f"the README says {stated.group(1)!r} sources; its table has {rows} rows")


def test_the_readme_headline_totals_match_its_own_tables():
    """"1,098 nodes. 1,287 edges." and two tables that add up to something else
    is the front page contradicting itself.

    Arithmetic only — no engine needed. The loader already reads its counts back
    from the engine and refuses to finish if they disagree; this catches the
    other half, where a table is edited and the headline is not.
    """
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(errors="replace")

    headline = re.search(r"\*\*([\d,]+) nodes\. ([\d,]+) edges\.", readme)
    assert headline, "the README no longer states node and edge totals in that shape"
    nodes, edges = (int(g.replace(",", "")) for g in headline.groups())

    def total(section: str) -> int:
        # `split(header)[1]` raises IndexError if a table header is reworded —
        # a traceback naming a list index, where the rest of this file (and
        # `spelling.Unspellable`) is careful to produce a sentence.
        header = f"| {section} | Count | |"
        parts = readme.split(header)
        assert len(parts) > 1, (
            f"the README no longer has a table headed {header!r}; if it was "
            f"reworded, this guard needs the new wording")
        block = parts[1].split("\n\n")[0]
        counts = re.findall(r"^\|\s*`\w+`\s*\|\s*([\d,]+)\s*\|", block, re.M)
        assert counts, f"no {section.lower()} rows found"
        return sum(int(c.replace(",", "")) for c in counts)

    assert total("Label") == nodes, (
        f"the README says {nodes:,} nodes; its label table adds to {total('Label'):,}")
    assert total("Edge") == edges, (
        f"the README says {edges:,} edges; its edge table adds to {total('Edge'):,}")


def test_the_front_page_is_inside_the_check():
    """README.md was excluded by an xfail reading "still the repo template —
    #67". #67 is the pull request that rewrote it, so the comment became false
    in the same commit that should have deleted the exclusion — and because
    `pytest.xfail()` raises imperatively, the body never ran and it reported
    xfail rather than xpass. Nothing flagged the staleness.

    The result was that the file whose entire subject is "a citation that
    resolves on the author's machine can be dangling in the branch the reviewer
    reads" no longer checked the front page: the one document where that error
    is worst, and the one most people read first.
    """
    assert ROOT / "README.md" in DOCS, "the front page is not in the checked set"


def test_the_readme_does_not_quote_a_test_count():
    """The count is gone, and this is what stops it coming back.

    Every PR that adds a test edited that one line, so four open branches all
    changed it to four different numbers and each conflicted with the others.
    The README's job is to say how to run the suite, not how big it is.

    Stronger than the check it replaces: the old one could only say a number
    had gone stale; this one cannot be satisfied by a stale number at all, and
    it never conflicts because every branch agrees on its absence.
    """
    readme = (ROOT / "README.md").read_text(errors="replace")
    stated = re.search(r"pytest[^\n]*?#\s*~?\s*([\d,]+)\s*tests", readme)
    assert not stated, (
        f"README.md quotes {stated.group(1)!r} tests in its quickstart. That "
        f"figure goes stale on every commit that adds one, and every branch "
        f"edits the same line. Say what the command does, not how many tests "
        f"it runs.")
