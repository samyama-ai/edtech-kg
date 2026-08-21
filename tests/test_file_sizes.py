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
# `Dockerfile` and `Makefile` carry no extension, so a glob list alone leaves
# them out of the primary guard. Named explicitly rather than left to the
# escape test below, which is the backstop and not the check.
REVIEWABLE_TYPES = ["*.py", "*.md", "*.cypher", "*.yaml", "*.yml", "*.toml",
                    "*.json", "*.sql", "*.sh", "*.cfg", "*.ini",
                    # `*/` prefixed as well as bare: a git pathspec of
                    # "Dockerfile" matches only at the repo ROOT, so one in
                    # `docker/` or `deploy/` was outside the guard.
                    "Dockerfile", "*/Dockerfile", "Makefile", "*/Makefile"]


def git(*args: str) -> str:
    """One place that shells out to git, so one place decides what a missing
    git means. Two callers disagreeing about that is how a guard errors on one
    machine and skips on another."""
    try:
        out = subprocess.run(["git", *args], cwd=ROOT,
                             capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.skip(f"git is unavailable or this is not a checkout: {exc}")
    return out.stdout


def pathspec_sets(types):
    """A pathspec list read as `(suffixes, basenames)`.

    Its own function so a test can drive it. `"*/Dockerfile".lstrip("*")` gives
    `"/Dockerfile"` — never a `Path.suffix` and never a `Path.name` — so the
    `*/` forms added so a NESTED Dockerfile would be covered silently matched
    nothing, and the coverage check stopped seeing them. Suffixes come from the
    `*.ext` forms only; everything else is matched by BASENAME, which is what
    "Dockerfile" and "*/Dockerfile" both mean to git.
    """
    suffixes = {t[1:] for t in types if t.startswith("*.")}
    named = {t.rsplit("/", 1)[-1] for t in types if not t.startswith("*.")}
    return suffixes, named


def tracked() -> list[str]:
    """Paths git knows about, NUL-separated.

    `-z` and a split on "\\0", not `.split()`, for the reason `names_from`
    gives.
    """
    return names_from(git("ls-files", "-z", *REVIEWABLE_TYPES))


def line_count(name: str) -> int | None:
    path = ROOT / name
    if not path.exists():
        return None
    # One decoding policy for every reader here. Two tests disagreeing about
    # `errors=` meant one could raise UnicodeDecodeError where the other passed.
    #
    # `errors="replace"` is right HERE and wrong in the link checker: this
    # function counts LINES, and a substituted U+FFFD does not change how many
    # there are. The link checker reads paths out of the text, where a
    # substitution silently changes what it is looking for.
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def test_no_source_file_is_too_large_to_review():
    oversized = [f"{name} ({count} lines)" for name in tracked()
                 if (count := line_count(name)) is not None
                 and count > REVIEWABLE_LINES and name not in OVERSIZED_ALREADY]
    assert not oversized, (
        f"review skips files over {REVIEWABLE_LINES} lines and blocks the PR. "
        f"Split by subject, not by length: {oversized}")


def parse_exceptions(source: str):
    r"""`OVERSIZED_ALREADY` out of a copy of this file, or None if it is not
    there at all.

    An EMPTY set is the goal state — #86 closed, nothing exempt — and the
    previous pattern `\{[^}]*\}` cannot match `set()`, which is how Python
    spells it. So the day the list is finally emptied on `main`, the baseline
    would read as "no baseline" and the ratchet would silently degrade to a
    skip: the one moment it most needs to hold.
    """
    import ast
    import re
    found = re.search(r"^OVERSIZED_ALREADY = (set\(\)|\{[^}]*\})", source, re.M)
    if not found:
        return None
    literal = found.group(1)
    return set() if literal == "set()" else set(ast.literal_eval(literal))


def baseline_exceptions():
    """`OVERSIZED_ALREADY` as it stands on the merge target, or None.

    **The baseline has to come from outside this file.** A frozen copy kept
    here alongside the live set is two literals three lines apart, and one
    commit editing both defeats the ratchet completely — which is what the
    previous version did while claiming to be a ratchet. `main` is merged
    history: a branch cannot edit it, so a list that only ever shrinks
    against it is a list that only ever shrinks.

    None when there is no baseline to read — the commit that first adds this
    file, or a clone with no `main`. Reported as a skip rather than a pass.

    `origin/main` is tried first and plain `main` second. In CI without a
    fetch, `origin/main` can be behind; `main` is then the better answer, and
    a baseline that is merely OLD is still a valid floor — the list may only
    shrink, so comparing against an older, larger list can only be more
    permissive, never wrongly strict.
    """
    for ref in ("origin/main", "main"):
        # `git show` is allowed to fail — the ref may not exist — so it does
        # NOT go through `git()`, which skips the test on any failure. A
        # missing BINARY still has to skip like everything else, though, so
        # that one case is asked first.
        git("rev-parse", "--git-dir")
        out = subprocess.run(["git", "show", f"{ref}:tests/test_file_sizes.py"],
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            continue
        found = parse_exceptions(out.stdout)
        if found is not None:
            return found
        # Resolved but held no list — an older copy of this file, or one that
        # predates the guard. Falling through to the next ref rather than
        # returning None: `origin/main` can be arbitrarily stale in an
        # unfetched checkout, and stopping there would skip the ratchet on the
        # strength of a ref nobody had updated.
    return None


def test_the_exception_list_only_shrinks():
    """An allowlist that can grow is a limit that does not exist.

    Membership, not length. `len(...) <= 2` is a cap, not a ratchet: split one
    of these files and the freed slot silently admits a different oversized
    file, which is exactly the "the exception quietly becomes the rule"
    outcome the module docstring promises against.

    Compared against the list on `main`, for the reason `baseline_exceptions`
    gives — a second literal in this file is not a baseline, it is a copy.
    """
    granted = baseline_exceptions()
    if granted is None:
        pytest.skip("no OVERSIZED_ALREADY on main yet — nothing to ratchet against")
    added = set(OVERSIZED_ALREADY) - granted
    assert not added, (
        f"these were added to the exception list, which may only shrink: "
        f"{sorted(added)}. Split the file instead; see #86")


def test_the_limit_itself_only_gets_stricter():
    """The exception list is ratcheted and the LIMIT was not.

    `REVIEWABLE_LINES = 900` defeats the whole guard in one line, without
    touching the allowlist the ratchet watches — a larger hole than any entry
    could open, and the one nobody was looking at. Compared against `main` for
    the same reason the list is: a branch cannot edit merged history.
    """
    import re
    for ref in ("origin/main", "main"):
        out = subprocess.run(["git", "show", f"{ref}:tests/test_file_sizes.py"],
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            continue
        found = re.search(r"^REVIEWABLE_LINES = (\d+)", out.stdout, re.M)
        if not found:
            continue
        assert REVIEWABLE_LINES <= int(found.group(1)), (
            f"the review limit was raised from {found.group(1)} to "
            f"{REVIEWABLE_LINES}. That exempts every file between the two "
            f"without adding one to the exception list — the ratchet watches "
            f"the list, so this is the way around it.")
        return
    pytest.skip("no REVIEWABLE_LINES on main yet — nothing to ratchet against")


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
    the same failure as a test file that does.

    Asserted as "every tracked file of a reviewable type is inside the guard",
    not as "a `.cypher` file exists". The latter is an assertion about repo
    CONTENT, so deleting the last schema file — a legitimate change — would
    fail a test about the guard's reach.
    """
    covered = set(tracked())
    every = names_from(git("ls-files", "-z"))
    suffixes, named = pathspec_sets(REVIEWABLE_TYPES)
    missed = sorted(name for name in every
                    if (Path(name).suffix in suffixes or Path(name).name in named)
                    and name not in covered)
    assert not missed, f"a reviewable type is not reaching the guard: {missed}"
    assert covered, "the guard is looking at nothing at all"


def test_no_tracked_text_file_escapes_the_limit_by_its_extension():
    """The guard listed three extensions, so everything else was exempt without
    saying so. A reviewer reads whatever is in the diff.

    Compared against what git actually tracks rather than a second list, so a
    new file type arriving in the repo shows up here instead of being quietly
    outside the limit.
    """
    everything = git("ls-files", "-z")
    covered = set(tracked())
    # Binaries and licence text are not review material; anything else is.
    exempt = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".xlsx",
              ".zip", ".gz", ".woff", ".woff2", ".lock"}
    escaping = sorted(
        name for name in names_from(everything)
        if name not in covered
        and Path(name).suffix.lower() not in exempt
        and Path(name).name not in {"LICENSE", ".gitignore"}
        and (count := line_count(name)) is not None and count > REVIEWABLE_LINES)
    assert not escaping, (
        f"these are over {REVIEWABLE_LINES} lines and outside the guard because "
        f"of their extension: {escaping}. Add the type to REVIEWABLE_TYPES.")


def test_the_ratchet_reads_a_baseline_and_notices_growth():
    """The ratchet itself, driven directly — on this branch the baseline test
    above SKIPS, because `main` does not carry this file yet, and a skipped
    guard proves nothing about the guard.

    The previous version kept a frozen copy of the list in this same file,
    three lines from the live one. Two literals in one file is not a ratchet:
    one commit editing both defeats it entirely, while the docstring goes on
    claiming the list may only shrink.
    """
    blob = ('REVIEWABLE_LINES = 500\n'
            'OVERSIZED_ALREADY = {"etl/probe_registry.py", "tests/test_probe_registry.py"}\n'
            'ROOT = 1\n')
    # THE parser, not a copy of it pasted here. Re-implementing the regex
    # inline meant this test could pass while the real function was broken —
    # the dead-path test this repo has shipped before.
    granted = parse_exceptions(blob)
    assert granted == {"etl/probe_registry.py", "tests/test_probe_registry.py"}

    # The goal state, which the previous pattern could not match at all.
    assert parse_exceptions("OVERSIZED_ALREADY = set()\n") == set()
    assert parse_exceptions("nothing here") is None

    # Shrinking is allowed; growing is not; SWAPPING is not — which is the
    # case a length check waves through.
    assert not ({"etl/probe_registry.py"} - granted), "shrinking must be allowed"
    assert {"etl/new_giant.py"} - granted, "a new entry must be caught"
    assert ({"etl/probe_registry.py", "etl/other.py"} - granted) == {"etl/other.py"}, \
        "a same-size swap must be caught"


def test_the_ratchet_baseline_is_not_read_from_this_file():
    """The property the ratchet rests on, and the one a test cannot observe.

    `test_the_exception_list_only_shrinks` SKIPS wherever `main` has no copy of
    this file yet — which is every branch that introduces it. So replacing
    `baseline_exceptions()` with a frozen literal, exactly the defect this was
    written to remove, makes the test pass rather than fail.

    Asserting on this module's own source is the honest way to check "where
    does the baseline come from", because that is a claim about the code rather
    than about its output.
    """
    import inspect
    source = inspect.getsource(test_the_exception_list_only_shrinks)
    assert "baseline_exceptions()" in source, (
        "the ratchet is comparing against something other than the baseline "
        "read from main — a second literal in this file is a copy, not a floor")
    assert "frozenset(" not in source and "OVERSIZED_ALREADY = {" not in source, (
        "a literal set has reappeared inside the ratchet test")


def test_the_named_pathspecs_are_matched_by_basename():
    """`"*/Dockerfile".lstrip("*")` gives `"/Dockerfile"` — never a `Path.suffix`
    and never a `Path.name`, so the `*/` forms added so a nested Dockerfile
    would be covered silently matched nothing, and the coverage check stopped
    seeing them at all.

    Driven directly, because the repo has no Dockerfile: the bug is in how the
    pathspec list is read, not in what the repo happens to contain.
    """
    suffixes, named = pathspec_sets(
        ["*.py", "Dockerfile", "*/Dockerfile", "*/Makefile"])
    assert suffixes == {".py"}, suffixes
    assert named == {"Dockerfile", "Makefile"}, named
    assert "/Dockerfile" not in named, "the leading slash is back"
