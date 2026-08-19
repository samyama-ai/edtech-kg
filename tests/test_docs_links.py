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
    text = document.read_text()
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
