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


# README.md is still the unmodified repo template and links {{KG_SLUG}}
# placeholders. Marked rather than excluded, so it stays visible in the report
# and disappears the moment #67 lands.
KNOWN_TEMPLATE = {"README.md"}


@pytest.mark.parametrize("document", DOCS, ids=lambda d: str(d.relative_to(ROOT)))
def test_every_file_a_document_cites_exists(document):
    if str(document.relative_to(ROOT)) in KNOWN_TEMPLATE:
        pytest.xfail("still the repo template — #67")
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
        block = readme.split(f"| {section} | Count | |")[1].split("\n\n")[0]
        counts = re.findall(r"^\|\s*`\w+`\s*\|\s*([\d,]+)\s*\|", block, re.M)
        assert counts, f"no {section.lower()} rows found"
        return sum(int(c.replace(",", "")) for c in counts)

    assert total("Label") == nodes, (
        f"the README says {nodes:,} nodes; its label table adds to {total('Label'):,}")
    assert total("Edge") == edges, (
        f"the README says {edges:,} edges; its edge table adds to {total('Edge'):,}")


REVIEWABLE_LINES = 500

# Already over the line when this guard was written, and tracked as #86. The
# list may only SHRINK — a test below fails if anything is added to it, so the
# exception cannot quietly become the rule.
OVERSIZED_ALREADY = {"etl/probe_registry.py", "tests/test_probe_registry.py"}


def test_no_source_file_is_too_large_to_review():
    """Review skips a file over 500 lines and marks the PR blocked.

    It has happened twice: a 529-line test file, and `test_schema_cypher.py` at
    599. Both times the file that went unread was a test file — the one
    asserting the findings everything else rests on.

    The limit is the reviewer's, not a style preference, so it belongs in the
    suite rather than in someone's memory.
    """
    root = Path(__file__).resolve().parents[1]
    tracked = subprocess.run(["git", "ls-files", "*.py", "*.md", "*.cypher"],
                             cwd=root, capture_output=True, text=True, check=True)
    oversized = []
    for name in tracked.stdout.split():
        path = root / name
        if not path.exists():
            continue
        count = len(path.read_text(errors="replace").splitlines())
        if count > REVIEWABLE_LINES and name not in OVERSIZED_ALREADY:
            oversized.append(f"{name} ({count} lines)")
    assert not oversized, (
        f"review skips files over {REVIEWABLE_LINES} lines and blocks the PR. "
        f"Split by subject, not by length: {oversized}")


def test_the_oversized_exception_list_only_shrinks():
    """An allowlist that can grow is a limit that does not exist.

    Anything added here is a file review will not read, and #86 is where that
    debt is tracked. When a file on this list is split, remove it — the test
    below notices if it stops being over the limit.
    """
    assert len(OVERSIZED_ALREADY) <= 2, (
        f"the exception list has grown to {len(OVERSIZED_ALREADY)}; see #86")

    root = Path(__file__).resolve().parents[1]
    fixed = [name for name in OVERSIZED_ALREADY
             if (root / name).exists()
             and len((root / name).read_text().splitlines()) <= REVIEWABLE_LINES]
    assert not fixed, (
        f"these are under the limit now and should come off the list: {fixed}")
