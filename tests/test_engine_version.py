"""What produced the figures, and whether it still would.

Every count in `README.md`, `docs/` and `demo/` was measured against one engine
build. A repo whose whole argument is its figures has to be able to say which
build that was, and to notice when it changes — edtech-kg#24.

The awkward fact this file exists to record: **the image tag and the engine
version are different numbers.** The image is tagged `1.1.0` and the binary
inside reports `1.7.0`. Sixty-odd places in this repo say "1.1.0" meaning the
tag, which is the thing a reader can pull. Nothing said so, and nothing checked
it, so "measured against 1.1.0" was ambiguous between two different claims.
"""

from __future__ import annotations

import os
import re
import subprocess
import urllib.error
from pathlib import Path

import pytest

from etl import engine

ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get("SAMYAMA_URL") or os.environ.get("SAMYAMA_TEST_URL")


def reachable() -> dict | None:
    if not URL:
        return None
    try:
        return engine.status(URL)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def test_the_engine_reports_the_version_this_repo_records():
    """The figures are attributed to a build. If the build changes, that
    attribution is wrong and every count needs re-measuring — so this is a
    failing test rather than a line in a document nobody re-reads.

    `SAMYAMA_REQUIRE_ENGINE=1` turns "no engine" into a failure. Skipping is
    how "verified against the engine" reaches a README on the strength of a run
    nobody made.
    """
    live = reachable()
    if live is None:
        message = f"no engine at {URL or 'SAMYAMA_URL / SAMYAMA_TEST_URL'}"
        if os.environ.get("SAMYAMA_REQUIRE_ENGINE") == "1":
            pytest.fail(f"{message} — SAMYAMA_REQUIRE_ENGINE=1 forbids skipping this")
        pytest.skip(message)

    assert live.get("version") == engine.ENGINE_VERSION, (
        f"the engine reports {live.get('version')!r} but etl/engine.py records "
        f"{engine.ENGINE_VERSION!r}. Every figure in this repo was measured "
        f"against the recorded build — re-measure before changing this constant, "
        f"and see the version-bump note in README.md.")


def test_the_recorded_version_is_not_the_image_tag():
    """The trap this whole file is about. If someone 'tidies' `ENGINE_VERSION`
    to match the tag, the constant stops describing the engine and the two
    claims silently merge back into one ambiguous number."""
    tag = engine.IMAGE.rsplit(":", 1)[1]
    assert engine.ENGINE_VERSION != tag, (
        f"ENGINE_VERSION and the image tag are both {tag!r}. They were "
        f"different when this was written — the tag is what you pull, the "
        f"version is what the binary calls itself. If the build genuinely "
        f"aligned them, delete this test and say so in the commit.")


def test_the_image_is_pinned_to_an_exact_tag():
    """A floating tag moves the engine under published figures with no commit
    to point at."""
    assert not engine.IMAGE.endswith(":latest"), f"{engine.IMAGE} floats"
    assert re.search(r":\d+\.\d+\.\d+$", engine.IMAGE), (
        f"{engine.IMAGE} is not pinned to an exact version")


def test_a_digest_is_recorded_because_a_tag_can_be_repushed():
    """The gap a tag cannot close: same name, different bytes. Without the
    digest, a reader who pulls `1.1.0` next month cannot tell whether they got
    what these figures were measured against."""
    assert engine.IMAGE_DIGEST.startswith("sha256:")
    assert len(engine.IMAGE_DIGEST.split(":")[1]) == 64, (
        f"not a full sha256: {engine.IMAGE_DIGEST}")


def test_every_documented_docker_run_uses_the_recorded_image():
    """Six files carry a `docker run` line, and they drifted apart before —
    which is how a reader ends up measuring against a different engine than the
    figures they are checking.

    Read out of the tracked files rather than listed here, so a new file with a
    seventh copy is covered the day it lands.
    """
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                             capture_output=True, text=True)
    if tracked.returncode != 0:
        pytest.skip("not a git checkout")

    wrong = []
    for name in (n for n in tracked.stdout.split("\0") if n):
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for found in re.finditer(r"samyama-graph:[\w.\-]+", body):
            image = "public.ecr.aws/f9f6l5u4/" + found.group(0)
            if image != engine.IMAGE:
                wrong.append(f"{name}: {found.group(0)}")

    assert not wrong, (
        f"these name an image other than the recorded {engine.IMAGE}: {wrong}. "
        f"One engine produced every figure in this repo; two would mean nobody "
        f"can say which.")


def test_the_readme_says_what_a_version_bump_means():
    """#24 asked for this in writing, and it is the part a constant cannot
    carry: what a reader should DO when the engine moves. Without it, the next
    person bumps the tag, sees green tests, and publishes figures measured
    against a build that no longer exists."""
    readme = (ROOT / "README.md").read_text(errors="replace")
    flat = " ".join(readme.split())
    assert engine.IMAGE_DIGEST[:23] in flat.replace(" ", ""), (
        "the README does not record the image digest")
    assert engine.ENGINE_VERSION in flat, (
        f"the README does not record that the engine reports "
        f"{engine.ENGINE_VERSION}")
    assert re.search(r"re-?measur", flat, re.I), (
        "the README does not say that a version bump means re-measuring — "
        "which is the only instruction that matters here")
