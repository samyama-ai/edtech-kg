"""`CONTRIBUTING.md` against what this repo actually does — edtech-kg#26.

A contributing guide is a document about the project's own habits, so it is
the easiest kind to write once and let rot. The conventions it states are
checked against real branches and real files rather than taken on trust.

The size table is checked against the run that produced it, in both
directions, which is the rule the page itself states. It is not RE-DERIVED
here — that needs a Gitea token and one API call per merged PR — which is
exactly the case the rule covers: commit the run, then test the page against
it.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import json

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "CONTRIBUTING.md"
RECORD = ROOT / "docs" / "sources" / "review-cost-measured.json"

#: The pattern the page states. Kept here as the one place a test compares
#: against, so a reworded page fails rather than quietly meaning something else.
BRANCH = re.compile(
    r"^(feat|fix|chore|docs|refactor|test|research)(\([^)]+\))?/\d+/[a-z0-9-]+$")


def page() -> str:
    assert PAGE.exists(), "CONTRIBUTING.md is gone (#26)"
    return PAGE.read_text(encoding="utf-8")


def test_it_is_short_enough_to_be_read():
    """#26's own definition of done. A contributing guide nobody finishes is a
    guide nobody follows, and `CLAUDE.md` already holds the long form."""
    lines = page().splitlines()
    assert len(lines) < 120, (
        f"CONTRIBUTING.md is {len(lines)} lines. The detail belongs in "
        f"CLAUDE.md; this file is the part someone reads once.")


def test_it_states_the_branch_convention_this_repo_uses():
    text = page()
    assert "<type>/<issue>/<kebab-description>" in text
    for kind in ("feat", "fix", "chore", "docs", "refactor", "test", "research"):
        assert kind in text, f"{kind} is used in this repo and is not listed"
    assert "Closes #" in text, "the auto-close convention is not stated"


def test_the_branch_convention_matches_the_branches_that_exist():
    """The check that keeps this honest. A convention no branch follows is
    aspiration; one every branch follows is a rule worth writing down."""
    listed = subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"],
        capture_output=True, text=True, cwd=ROOT)
    # Filtered AFTER the split, not before. `for-each-ref` prints the HEAD
    # symref with the short name `origin`, not `origin/HEAD`, so a guard on
    # the pre-split name missed it and a bare `origin` reached the branch
    # check — a ref that can never match, named in the failure message as a
    # branch breaking the convention.
    names = [n.split("origin/", 1)[-1] for n in listed.stdout.split()]
    names = [n for n in names if n not in ("origin", "HEAD", "main")]
    if not names:
        pytest.skip("no remote branches fetched")
    matching = [n for n in names if BRANCH.match(n)]
    # Not "all": `chore/readme-test-count` predates the rule and is merged.
    # A ratchet on the SHARE, so a new branch that ignores it moves the number.
    assert len(matching) / len(names) >= 0.8, (
        f"only {len(matching)} of {len(names)} branches follow the convention "
        f"CONTRIBUTING.md states: {[n for n in names if n not in matching]}")


def test_it_states_the_evidence_standard():
    """#26's definition of done names this specifically: measured is labelled
    measured, estimated is labelled estimated, counts come from scripts."""
    text = page().lower()
    for phrase in ("measured is labelled measured",
                   "printed by a probe, never typed",
                   "raw data is never committed"):
        assert phrase in text, f"the evidence standard omits: {phrase!r}"


def test_it_names_the_things_that_actually_bite():
    """Each of these cost this repo real review rounds. A guide that omits
    them is a guide written from first principles rather than from history."""
    text = page().lower()
    for phrase in ("mutation-test", "500 lines", "python3.11",
                   "samyama_test_url"):
        assert phrase in text, f"CONTRIBUTING.md does not mention {phrase!r}"


def test_the_commands_it_gives_are_the_ones_that_work():
    """A guide whose command is wrong is worse than one with no command."""
    text = page()
    assert "python3.11 -m pytest" in text, (
        "the suite command must name python3.11 — the default python3 on this "
        "machine is 3.14 with none of the dependencies")
    assert "SAMYAMA_TEST_URL" in text and "SAMYAMA_URL" in text, (
        "both variables are needed; setting one leaves engine tests skipping")


def test_it_does_not_cite_a_document_a_reader_cannot_open():
    """It linked `CLAUDE.md`, which is in no checkout but mine.

    The file is excluded LOCALLY — `.git/info/exclude`, not `.gitignore` — so
    it sits on one machine and in nobody else's tree. `test_docs_links` caught
    the dangling link correctly and I never saw it, because the file was there
    when I ran the suite. The same shape as an engine test skipping into a
    green run: a check passing on something in my environment.

    Named rather than linked would still send a reader to a file they cannot
    get, so the page stands alone instead.
    """
    text = page()
    assert "](CLAUDE.md)" not in text, (
        "CONTRIBUTING.md links CLAUDE.md, which is excluded from the repo and "
        "exists in no checkout — this is what turned main red")
    assert "stands alone" in text, (
        "the page defers to a document a reader cannot open")


# --------------------------------------------------------------------------
# The size table against the run that produced it. This page is the first in
# the repo to state "every figure is printed by a probe, never typed" as
# policy, so it is the worst possible place for a typed figure.
# --------------------------------------------------------------------------

def measured() -> dict:
    assert RECORD.exists(), (
        "the size table has no committed run, so its figures are typed — "
        "which this page's own evidence standard forbids")
    return json.loads(RECORD.read_text(encoding="utf-8"))


def table_rows(text: str) -> dict:
    """The size table as the page states it."""
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip("| ").split("|")]
        if len(cells) == 4 and re.match(r"^(under|over|\d)", cells[0]):
            try:
                rows[cells[0].replace("\u2013", "-")] = {
                    "prs": int(cells[1]),
                    "mean_rounds": float(cells[2].strip("*")),
                    "worst": int(cells[3])}
            except ValueError:
                continue
    return rows


def test_every_figure_in_the_table_is_in_the_record():
    """A number on the page that is not in the run is one somebody typed."""
    record, stated = measured(), table_rows(page())
    assert stated, "the size table could not be read off the page"
    for band, row in stated.items():
        assert band in record["bands"], f"the page states a band the run has no {band!r}"
        assert row == record["bands"][band], (
            f"{band}: page says {row}, the run says {record['bands'][band]}")


def test_every_band_in_the_record_is_on_the_page():
    """And the other direction. A band measured and not published is a band
    the reader cannot see — and dropping the worst one would be the tempting
    omission."""
    record, stated = measured(), table_rows(page())
    missing = set(record["bands"]) - set(stated)
    assert not missing, f"measured and not published: {sorted(missing)}"


def test_the_page_states_how_many_prs_the_table_rests_on():
    record = measured()
    assert f"{record['pull_requests']} merged PRs" in page(), (
        "the page does not say how many PRs the table counts, so a reader "
        "cannot tell nine PRs from ninety")


def test_the_page_names_the_command_that_refreshes_it():
    """"If you cannot point at the command, delete the figure" — this page's
    own words, applied to this page."""
    assert "python -m etl.probe_review_cost" in page()


def test_the_bands_the_probe_uses_are_the_bands_the_page_shows():
    """Two copies of a boundary is how a page ends up describing bands the
    probe never computed."""
    from etl import probe_review_cost

    assert set(table_rows(page())) == {name for _, name in probe_review_cost.BANDS}


def test_a_band_boundary_is_decided_in_one_place():
    """Driven, so the mapping is exercised rather than read."""
    from etl import probe_review_cost as p

    assert p.band(249) == "under 250"
    assert p.band(250) == "250-700"
    assert p.band(699) == "250-700"
    assert p.band(1500) == "over 1500"


def test_a_walk_that_found_no_pull_requests_is_refused(monkeypatch):
    """Zero PRs would print an empty table under a heading claiming evidence."""
    from etl import probe_review_cost as p

    monkeypatch.setattr(p, "merged_sizes", lambda: ({}, []))
    with pytest.raises(p.Unreachable, match="no merge commits"):
        p.probe(quiet=True)


def test_a_missing_token_is_named_rather_than_a_traceback(monkeypatch):
    """It reads a private forge. Someone without a token should be told that,
    not shown a 401."""
    from etl import probe_review_cost as p

    monkeypatch.delenv("GITEA_TOKEN", raising=False)
    monkeypatch.delenv("SAMYAMA_GITEA_TOKEN", raising=False)
    with pytest.raises(p.Unreachable, match="no Gitea token"):
        p.token()


# --------------------------------------------------------------------------
# Driving the probe. `merged_sizes` had no test at all, and it is the function
# that decides which PR a size belongs to.
# --------------------------------------------------------------------------

def test_a_pr_number_comes_from_the_merge_form_not_the_first_hash(monkeypatch):
    """The defect: `#(\d+)` took the first `#N` in the line, and this repo's
    titles reference issues in prose constantly — this probe's own docstring
    says `edtech-kg#26`. The first such title would have attributed another
    PR's review rounds to it, silently, and the table would still look right.
    """
    from etl import probe_review_cost as p

    subjects = [
        "aaaaaaa\tMerge pull request 'chore: close #26 properly' (#117) from x into main",
        "bbbbbbb\tMerge pull request 'fix: thing' (#99) from y into main",
        "ccccccc\tMerge remote-tracking branch 'origin/main' into feat/18/ci",
    ]

    def fake_run(args, **kwargs):
        class Result:
            stdout = ("\n".join(subjects) if "log" in args
                      else " 3 files changed, 42 insertions(+)")
        return Result()

    monkeypatch.setattr(p.subprocess, "run", fake_run)
    sizes, skipped = p.merged_sizes()
    assert set(sizes) == {117, 99}, (
        f"the PR numbers read were {sorted(sizes)} — a title mentioning #26 "
        f"must not be read as PR 26")
    assert len(skipped) == 1 and "names no PR" in skipped[0]


def test_a_merge_with_no_insertions_is_reported_not_dropped(monkeypatch):
    """A partially dropped walk produces a table that looks complete."""
    from etl import probe_review_cost as p

    def fake_run(args, **kwargs):
        class Result:
            stdout = ("aaaaaaa\tMerge pull request 'x' (#5) from y into main"
                      if "log" in args else " 1 file changed, 2 deletions(-)")
        return Result()

    monkeypatch.setattr(p.subprocess, "run", fake_run)
    sizes, skipped = p.merged_sizes()
    assert not sizes
    assert skipped and "#5" in skipped[0]


def test_a_bad_token_is_named_rather_than_retried_as_unreachable(monkeypatch):
    """`HTTPError` subclasses `URLError`, so a 401 burned four attempts with
    backoff and then reported that the forge "did not answer" — the wrong
    diagnosis for the likeliest failure, arrived at slowly."""
    import urllib.error

    from etl import probe_review_cost as p

    slept = []
    monkeypatch.setattr(p.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(p, "token", lambda: "nope")

    def refuse(request, timeout=30):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(p.urllib.request, "urlopen", refuse)
    with pytest.raises(p.Unreachable, match="401"):
        p.get("/pulls/1/reviews")
    assert not slept, "a 401 was retried; it will never become a 200"


def test_a_server_error_is_still_retried(monkeypatch):
    """The other side of that check, or 5xx stops being tolerated."""
    import urllib.error

    from etl import probe_review_cost as p

    slept = []
    monkeypatch.setattr(p.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(p, "token", lambda: "yes")

    def refuse(request, timeout=30):
        raise urllib.error.HTTPError(request.full_url, 503, "Unavailable", {}, None)

    monkeypatch.setattr(p.urllib.request, "urlopen", refuse)
    with pytest.raises(p.Unreachable, match="503"):
        p.get("/pulls/1/reviews")
    assert slept, "a 503 was not retried"


def test_the_page_says_how_many_merges_were_skipped():
    """Silent truncation reads as complete coverage."""
    assert str(measured()["merges_skipped"]) in page(), (
        "the page does not say how many merges the walk skipped")

