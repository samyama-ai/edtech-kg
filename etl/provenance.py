"""Which code produced a measurement.

`DATASET-CARD.md` says the code version is "this repository, at the commit that
produced the records". Nothing recorded that commit, so the claim could not be
checked — and a figure in `docs/sources/` could not be traced back to the code
that printed it. Twelve records, none carrying a version. That is the same shape
as a docstring asserting a guard the code does not implement: a claim in prose
with nothing behind it.

**The commit that CONTAINS a record cannot be inside it.** The hash is not known
until after the file is written and committed. What is knowable, and what
actually answers the question, is the commit the working tree was at WHEN THE
PROBE RAN, and whether that tree was clean. A record stamped `dirty: true` was
produced by code that is not in any commit, which is worth knowing before
quoting its figures.

No third-party dependency: `git` is asked directly, and a missing `git` or a
tarball with no `.git` degrades to `unknown` rather than raising. A probe must
not fail because it could not describe itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str | None:
    """Ask git, inside this repo only.

    `git -C <dir>` inherits git's upward directory search, so a non-editable
    install into a venv nested in someone else's project answers from THAT
    repo and stamps its commit as ours — worse than the `unknown` this module
    promises, because it is confidently wrong.
    """
    if not _inside_our_repo():
        return None
    try:
        out = subprocess.run(("git", "-C", str(ROOT)) + args,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@lru_cache(maxsize=1)
def _inside_our_repo() -> bool:
    """Is ROOT itself a git work tree, rather than something above it?"""
    try:
        out = subprocess.run(("git", "-C", str(ROOT), "rev-parse",
                              "--show-toplevel"),
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    if out.returncode != 0:
        return False
    try:
        return Path(out.stdout.strip()).resolve() == ROOT
    except OSError:
        return False


@lru_cache(maxsize=1)
def _code_version() -> dict:
    """The code that produced a record, as far as it can be known.

    Cached: every probe calls it once per run, and shelling out to git for each
    of several records in one run is the same answer three times.
    """
    commit = _git("rev-parse", "HEAD")
    # **Scoped to the code, not the tree.** `git status --porcelain` with no
    # pathspec reports a modified record as a dirty tree — and the workflow this
    # repo documents (state-access.md, ceds.md, licences.md) is to refresh
    # records ONE AT A TIME. So from a clean checkout, `probe_ceds --record`
    # writes one file and the very next probe stamps `dirty: true` although
    # every line of etl/ and schema/ is committed and unmodified. Any untracked
    # scratch file anywhere did the same. That is false provenance written into
    # the record, in the exact workflow the docs prescribe.
    status = _git("status", "--porcelain", "--", "etl", "schema")
    try:
        package = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        package = "unknown"

    return {
        "commit": commit or "unknown",
        # None means git did not answer at all, which is not the same as clean.
        "dirty": None if status is None else bool(status),
        "package": package,
        "_": ("The commit the tree was at when this probe ran — not the commit "
              "that contains this file, which cannot be known before it is "
              "written. `dirty: true` means uncommitted changes were present."),
    }


def code_version() -> dict:
    """A fresh dict each call.

    `@lru_cache` returns the *same* object every time, and `write_record`
    embeds it in each payload — so one caller mutating the stamp would poison
    every later record in the process. The cache is on the private function;
    this hands out copies.
    """
    return dict(_code_version())


def write_record(path: Path, payload: dict) -> None:
    """Write a measured record, stamped with the code that produced it.

    One writer rather than eleven. Every probe wrote its own `json.dumps` with
    its own arguments, and three of the eleven were already writing without
    `ensure_ascii=False` — so a record with an em-dash in it came out as
    `\\u2014` in some files and as the character in others, for no reason
    anyone chose.

    The stamp goes on LAST so a payload cannot overwrite it by accident: a probe
    that happens to carry its own `code` key would otherwise silently replace
    the provenance with something that is not it.
    """
    # The directory too. Six probes did this immediately above the call and
    # five did not, so whether a probe worked in a fresh checkout depended on
    # which one you ran. The argument for centralising the write applies
    # verbatim to centralising the directory it writes into.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written aside and moved into place. One writer for all thirteen records
    # writing in place means a Ctrl-C mid-write truncates a record that was
    # correct and committed a moment earlier — and these are the files the docs
    # quote. `etl/probe_pwcs.py` already writes this way; centralising the write
    # is the natural place to apply it rather than the place to drop it.
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps({**payload, "code": code_version()},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    partial.replace(path)


def commit_that_committed(path: Path) -> str | None:
    """The commit that last changed a file, or None if git cannot say.

    Used only by `backfill_stamp`. Deliberately separate from `code_version`,
    which answers a different question — *what was the tree when the probe
    ran* — and must not learn to guess.
    """
    if not _inside_our_repo():
        return None
    return _git("log", "-1", "--format=%H", "--", str(path)) or None


def backfill_stamp(path: Path) -> dict | None:
    """A stamp for a record that was measured before the writer stamped them.

    **This is weaker evidence than a live stamp, and says so in the record.**
    A live stamp names the tree the probe actually ran against. This names the
    commit that CONTAINS the record — which git knows for certain, but which
    only bounds the code that produced it rather than identifying it. The
    `backfilled` key exists so nobody reads one as the other later.

    Why it is needed at all: #171 landed the writer while #173 and #175 were
    already in flight, so three records were measured against a tree where
    `write_record` did not yet exist. Re-running is the better fix and was
    tried first — Census TIGER answered HTTP 520 on 2026-09-07, so geography
    cannot be re-measured today, and a repo whose suite goes red when a
    third-party host has an outage is a worse failure than an honest
    annotation.

    Returns None when git cannot name a commit, so the caller can refuse
    rather than write a stamp with a hole in it.
    """
    commit = commit_that_committed(path)
    if not commit:
        return None
    return {
        "commit": commit,
        # A committed file is by definition not dirty in the tree that holds
        # it. Stated rather than copied from `code_version()`, which would
        # report on THIS working tree and mean nothing about the record.
        "dirty": False,
        "package": _code_version().get("package"),
        "backfilled": (
            "The commit that CONTAINS this record, not the tree the probe ran "
            "against — the record predates `write_record`. Weaker than a live "
            "stamp: it bounds the code that produced these figures rather "
            "than naming it. Re-running the probe replaces this."),
    }


def main(argv: list[str] | None = None) -> int:
    """Backfill a stamp onto a record that predates the stamped writer.

        python -m etl.provenance --backfill docs/sources/geography-measured.json

    A CLI rather than a one-off script, because the first backfill here WAS a
    one-off script and that is the whole objection to it: the records changed,
    and nothing committed could say how. This repo's rule for figures — every
    one printed by something committed, never typed — applies to provenance at
    least as strongly as to counts.

    It refuses a record that already carries a stamp. Overwriting a live stamp
    with a backfilled one would replace strong evidence with weak and look
    like a routine re-run in the diff.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="python -m etl.provenance")
    parser.add_argument("--backfill", metavar="RECORD", required=True,
                        type=Path, help="the .json record to stamp")
    args = parser.parse_args(argv)

    record = args.backfill if args.backfill.is_absolute() else ROOT / args.backfill
    if not record.exists():
        print(f"no such record: {record}", file=sys.stderr)
        return 2

    payload = json.loads(record.read_text(encoding="utf-8"))
    if "code" in payload:
        print(f"{record.name} already carries a stamp — refusing to overwrite "
              f"it. Re-run the probe instead.", file=sys.stderr)
        return 3

    stamp = backfill_stamp(record)
    if not stamp:
        print(f"git cannot name a commit for {record.name}; a stamp with a "
              f"hole in it is worse than none.", file=sys.stderr)
        return 4

    record.write_text(
        json.dumps({**payload, "code": stamp}, indent=2, ensure_ascii=False)
        + "\n", encoding="utf-8")
    print(f"{record.name}: backfilled {stamp['commit'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
