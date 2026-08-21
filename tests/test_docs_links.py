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
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = sorted(ROOT.glob("docs/**/*.md")) + sorted(ROOT.glob("*.md"))

# `[text](path)` and bare `path` in backticks, skipping URLs and anchors.
LINK = re.compile(r"\[[^\]]*\]\((?!https?:|#)([^)#]+)")
BACKTICK = re.compile(r"`((?:docs/|etl/|schema/|tests/)[\w\-./]+\.\w+)`")


def references(document: Path):
    text = document.read_text(errors="replace")
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


REVIEWABLE_LINES = 500

# Already over the line when this guard was written, and tracked as #86. The
# list may only SHRINK — a test below fails if anything is added to it, so the
# exception cannot quietly become the rule.
OVERSIZED_ALREADY = {"etl/probe_registry.py", "tests/test_probe_registry.py"}


def names_from(stdout: str) -> list[str]:
    """Split `git ls-files -z` output.

    Its own function so a test can drive it, rather than being a line inside
    `tracked_files()` that only a repo containing a space in a path could
    exercise. Splitting a NUL-separated list on whitespace breaks
    `docs/course catalogue.md` into two names that exist nowhere — and because
    neither resolves on disk, the size guard skips both and reports nothing.
    A file too large to review would pass this suite purely for being named
    with a space in it.
    """
    return [name for name in stdout.split("\0") if name]


def tracked_files() -> list[str]:
    """Paths git knows about, NUL-separated."""
    out = subprocess.run(["git", "ls-files", "-z", "*.py", "*.md", "*.cypher"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return names_from(out.stdout)


def line_count(name: str):
    """Lines in a tracked file, or None if git lists it but it is not on disk.

    One decoding policy for every reader here. Two of them disagreeing about
    `errors=` meant one could raise UnicodeDecodeError where the other passed.
    """
    path = ROOT / name
    if not path.exists():
        return None
    return len(path.read_text(errors="replace").splitlines())


def test_no_file_is_too_large_to_review():
    """Review skips a file over 500 lines and marks the PR blocked.

    It has happened twice: a 529-line test file, and `test_schema_cypher.py` at
    599. Both times the file that went unread was a test file — the one
    asserting the findings everything else rests on.

    Documents count too, which is why the limit is applied to `*.md`. The limit
    is the reviewer's reading capacity, not a style rule about code, and a
    document that goes unread is the same failure as a test file that does.

    The limit is the reviewer's, not a style preference, so it belongs in the
    suite rather than in someone's memory.
    """
    oversized = [f"{name} ({count} lines)" for name in tracked_files()
                 if (count := line_count(name)) is not None
                 and count > REVIEWABLE_LINES and name not in OVERSIZED_ALREADY]
    assert not oversized, (
        f"review skips files over {REVIEWABLE_LINES} lines and blocks the PR. "
        f"Split by subject, not by length: {oversized}")


def test_the_oversized_exception_list_only_shrinks():
    """An allowlist that can grow is a limit that does not exist.

    Membership, not length. A count of "at most 2" is a fixed cap and not a
    ratchet: split one of these files, and the freed slot silently admits some
    other oversized file at the next commit — which is precisely the "the
    exception quietly becomes the rule" outcome the docstring promises against.
    Pinning the names means the list can only ever get shorter.

    Anything on it is a file review will not read, and #86 is where that debt
    is tracked.
    """
    granted = {"etl/probe_registry.py", "tests/test_probe_registry.py"}
    added = OVERSIZED_ALREADY - granted
    assert not added, (
        f"these were added to the exception list, which may only shrink: "
        f"{sorted(added)}. Split the file instead; see #86")


def test_no_exception_is_stale():
    """An entry now under the limit, or deleted, is a stale exception nobody
    will notice — so it fails rather than lingering."""
    stale = []
    for name in sorted(OVERSIZED_ALREADY):
        count = line_count(name)
        if count is None:
            stale.append(f"{name} (deleted)")
        elif count <= REVIEWABLE_LINES:
            stale.append(f"{name} ({count} lines — under the limit now)")
    assert not stale, f"remove these from OVERSIZED_ALREADY: {stale}"


def test_a_path_with_a_space_survives_the_split():
    """`git ls-files` was read with `.split()`, which is whitespace-splitting a
    NUL-separated list. `docs/course catalogue.md` became two names, neither of
    which resolves on disk, so `line_count` returned None for both and the file
    was skipped — silently, and by the guard whose whole job is to notice it.

    No file in this repo has a space in its path today, which is the only
    reason the defect never fired. That is exactly when to pin it.
    """
    assert names_from("a.py\0docs/course catalogue.md\0b.md\0") == [
        "a.py", "docs/course catalogue.md", "b.md"]
    assert names_from("") == []


def test_the_size_guard_reads_documents_as_well_as_code():
    """The limit is the reviewer's reading capacity, so it applies to prose."""
    listed = tracked_files()
    assert any(name.endswith(".md") for name in listed), listed[:5]
    assert any(name.endswith(".py") for name in listed), listed[:5]
    assert any(name.endswith(".cypher") for name in listed), listed[:5]
