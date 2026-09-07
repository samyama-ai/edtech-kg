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
import tomllib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(("git", "-C", str(ROOT)) + args,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@lru_cache(maxsize=1)
def code_version() -> dict:
    """The code that produced a record, as far as it can be known.

    Cached: every probe calls it once per run, and shelling out to git for each
    of several records in one run is the same answer three times.
    """
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
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
    path.write_text(
        json.dumps({**payload, "code": code_version()},
                   indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
