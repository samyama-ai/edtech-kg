"""No file may be too large for review to read.

Review skips any file over 500 lines and marks the PR blocked. It has happened
four times in this repo:

  * a 529-line test file, skipped once
  * `tests/test_schema_cypher.py` at 599, skipped whole in #68
  * `etl/load_pwcs.py` at 616, which #82 would have lost the same way
  * `tests/test_probe_bls.py` at 545, which blocked #71 on its own

Every one was a test file or the file its tests were about — the thing the
findings rest on, going unread.

Its own file, not folded into another. The guard is unrelated to what any other
test module is about, and a check that lives in an unrelated file is one nobody
finds when it fires.

The limit is the reviewer's, not a style preference, so it belongs in the suite
rather than in someone's memory. Remembering it failed four times.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REVIEWABLE_LINES = 500

# Already over the line when this guard was written, tracked as #86. The list
# may only SHRINK — a test below fails if anything is added to it, so the
# exception cannot quietly become the rule.
OVERSIZED_ALREADY = {"etl/probe_registry.py", "tests/test_probe_registry.py"}

ROOT = Path(__file__).resolve().parents[1]


def names_from(stdout: str) -> list[str]:
    """Split `git ls-files -z` output.

    Its own function so a test can drive it, rather than a line inside
    `tracked()` that only a repo containing a space in a path could exercise.
    Splitting a NUL-separated list on whitespace breaks `docs/course
    catalogue.md` into two names that resolve nowhere — and because neither is
    on disk, this guard skips both and reports nothing. A file too large to
    review would pass purely for being named with a space in it.
    """
    return [name for name in stdout.split("\0") if name]


# Every text type this repo tracks that a reviewer would have to read. Listing
# only `*.py`, `*.md` and `*.cypher` exempted everything else in silence — a
# 900-line workflow or a hand-written fixture is exactly as unreadable as a
# 900-line test, and would have passed this guard without appearing anywhere.
REVIEWABLE_TYPES = ["*.py", "*.md", "*.cypher", "*.yaml", "*.yml", "*.toml",
                    "*.json", "*.sql", "*.sh", "*.cfg", "*.ini"]


def tracked() -> list[str]:
    """Paths git knows about, NUL-separated.

    `-z` and a split on "\\0", not `.split()`, for the reason `names_from`
    gives. Skipped rather than failed outside a git checkout: run from an
    sdist or a tarball there is no index to read, and `check=True` would raise
    CalledProcessError where "this guard cannot run here" is the honest answer.
    """
    try:
        out = subprocess.run(["git", "ls-files", "-z", *REVIEWABLE_TYPES],
                             cwd=ROOT, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(f"not a git checkout, so the tracked file list is unavailable: {exc}")
    return names_from(out.stdout)


def line_count(name: str) -> int | None:
    path = ROOT / name
    if not path.exists():
        return None
    # One decoding policy for every reader here. Two tests disagreeing about
    # `errors=` meant one could raise UnicodeDecodeError where the other passed.
    return len(path.read_text(errors="replace").splitlines())


def test_no_source_file_is_too_large_to_review():
    oversized = [f"{name} ({count} lines)" for name in tracked()
                 if (count := line_count(name)) is not None
                 and count > REVIEWABLE_LINES and name not in OVERSIZED_ALREADY]
    assert not oversized, (
        f"review skips files over {REVIEWABLE_LINES} lines and blocks the PR. "
        f"Split by subject, not by length: {oversized}")


# The two that were already over the line when this guard was written. Frozen
# here so the list above can be compared against it rather than counted.
GRANTED = frozenset({"etl/probe_registry.py", "tests/test_probe_registry.py"})


def test_the_exception_list_only_shrinks():
    """An allowlist that can grow is a limit that does not exist.

    Membership, not length. `len(...) <= 2` is a fixed cap and not a ratchet:
    split one of these files and the freed slot silently admits a different
    oversized file, which is exactly the "the exception quietly becomes the
    rule" outcome the module docstring promises against. Comparing against a
    frozen set means the list can only ever get shorter.
    """
    added = set(OVERSIZED_ALREADY) - GRANTED
    assert not added, (
        f"these were added to the exception list, which may only shrink: "
        f"{sorted(added)}. Split the file instead; see #86")


def test_no_exception_is_stale():
    """An entry that is now under the limit, or has been deleted, is a stale
    exception nobody will notice — so it fails rather than lingering."""
    stale = []
    for name in OVERSIZED_ALREADY:
        count = line_count(name)
        if count is None:
            stale.append(f"{name} (deleted)")
        elif count <= REVIEWABLE_LINES:
            stale.append(f"{name} ({count} lines — under the limit now)")
    assert not stale, f"remove these from OVERSIZED_ALREADY: {stale}"


def test_a_path_with_a_space_survives_the_split():
    """`git ls-files` was once read with `.split()`, which whitespace-splits a
    NUL-separated list. `docs/course catalogue.md` became two names, neither
    resolving on disk, so `line_count` returned None for both and the file was
    skipped — silently, by the guard whose whole job is to notice it.

    No path in this repo has a space in it today, which is the only reason the
    defect never fired. That is exactly when to pin it.
    """
    assert names_from("a.py\0docs/course catalogue.md\0b.md\0") == [
        "a.py", "docs/course catalogue.md", "b.md"]
    assert names_from("") == []


def test_the_limit_covers_documents_as_well_as_code():
    """The limit is the reviewer's reading capacity, not a style rule about
    code, so prose and the schema are inside it. A document that goes unread is
    the same failure as a test file that does."""
    listed = tracked()
    for suffix in (".py", ".md", ".cypher"):
        assert any(name.endswith(suffix) for name in listed), (suffix, listed[:5])


def test_no_tracked_text_file_escapes_the_limit_by_its_extension():
    """The guard listed three extensions, so everything else was exempt without
    saying so. A reviewer reads whatever is in the diff.

    Compared against what git actually tracks rather than a second list, so a
    new file type arriving in the repo shows up here instead of being quietly
    outside the limit.
    """
    everything = subprocess.run(["git", "ls-files", "-z"],
                                cwd=ROOT, capture_output=True, text=True)
    if everything.returncode != 0:
        pytest.skip("not a git checkout")
    covered = set(tracked())
    # Binaries and licence text are not review material; anything else is.
    exempt = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".xlsx",
              ".zip", ".gz", ".woff", ".woff2", ".lock"}
    escaping = sorted(
        name for name in names_from(everything.stdout)
        if name not in covered
        and Path(name).suffix.lower() not in exempt
        and Path(name).name not in {"LICENSE", ".gitignore"}
        and (count := line_count(name)) is not None and count > REVIEWABLE_LINES)
    assert not escaping, (
        f"these are over {REVIEWABLE_LINES} lines and outside the guard because "
        f"of their extension: {escaping}. Add the type to REVIEWABLE_TYPES.")
