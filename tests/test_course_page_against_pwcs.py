"""THE CONTROL: run `course_page.classify` over PWCS's real markup.

**This is the guard that was missing, and it is the one that would have caught
the sentinel bug.** PWCS is the control this whole comparison rests on, and
its row in `second-district-measured.json` is produced by the same `classify`
under test — so if the classifier drifts, the fix is `--record`, the record
and the page move together, and the doc tests stay green. A probe validated
against its own output is not validated.

Two properties are checked against something OUTSIDE this module:

  * `etl/probe_pwcs.py` has its own, independently written prerequisite
    pattern. Both read the same 960 pages, so they must agree about which
    pages carry a typed prerequisite.
  * A page whose prerequisite field says "None" must not count as stating
    one. `docs/sources/course-prerequisites.md` records that mistake as a
    past correction, and this repo made it a second time.

Cache-gated, like every other test over this corpus: `data/` is gitignored, so
a fresh clone skips rather than fetching 960 pages from a school district.
"""

from __future__ import annotations

import hashlib
import pathlib
import re

import pytest

from etl import course_page
from etl.pwcs_pages import segments
from etl import probe_pwcs as source

CACHE = pathlib.Path(__file__).resolve().parents[1] / "data" / "pwcs"
BASE = "https://catalog.pwcs.edu"


def cache_is_complete() -> bool:
    """Every page the sitemap lists is on disk — the same gate the sibling
    tests use, and for the same reason."""
    if not CACHE.exists():
        return False
    try:
        urls = source.catalogue_urls(True)
    except Exception:                      # noqa: BLE001 — no cached sitemap
        return False
    return bool(urls) and all(source.cached_path(u).exists() for u in urls)


needs_cache = pytest.mark.skipif(
    not cache_is_complete(),
    reason="the cached catalogue is incomplete — run "
           "`python -m etl.probe_pwcs --record` to populate data/pwcs")


def course_pages() -> list[tuple[str, str]]:
    """(url, markup) for every cached page at course depth."""
    found = []
    for url in source.catalogue_urls(True):
        if len(segments(url)) != 2:
            continue
        path = source.cached_path(url)
        if path.exists():
            found.append((url, path.read_text(encoding="utf-8", errors="replace")))
    return found


@needs_cache
def test_classify_agrees_with_the_repos_own_prerequisite_pattern():
    """**Two independently written patterns over one corpus.**

    `etl/probe_pwcs.py` looks for the prerequisite block its own way. If
    `course_page` finds a typed prerequisite on a page that one does not — or
    misses one it finds — one of them is wrong, and nothing else in this
    suite can tell.
    """
    from etl.probe_pwcs import PREREQ_BLOCK

    pages = course_pages()
    assert len(pages) > 500, f"only {len(pages)} course pages cached"

    disagreed = []
    for url, markup in pages:
        theirs = bool(PREREQ_BLOCK.search(markup))
        ours = course_page.classify(markup, set())["kind"] == "typed"
        if theirs != ours:
            disagreed.append((url, theirs, ours))

    assert not disagreed[:20], (
        f"{len(disagreed)} of {len(pages)} pages are classified differently "
        f"by etl/probe_pwcs.py and etl/course_page.py. Two patterns over one "
        f"corpus disagreeing means one is wrong, and the record cannot say "
        f"which because it is written by the second.\n"
        + "\n".join(f"  {u} probe_pwcs={t} course_page={o}"
                    for u, t, o in disagreed[:5]))


@needs_cache
def test_a_page_saying_none_does_not_count_as_stating_a_prerequisite():
    """**The bug this file exists for.**

    The sentinel was an exact match on four strings, so `None.` — with a
    trailing full stop — counted as a stated prerequisite.
    `course-prerequisites.md` records the same mistake as a past correction:
    *"counted 'Prerequisite: None' as a stated prerequisite"*.
    """
    denials = re.compile(r"^\s*(prerequisites?\s*[:\-]?\s*)?(none|n/?a)\s*[.;:]?\s*$",
                         re.I)
    wrong = []
    for url, markup in course_pages():
        found = course_page.classify(markup, set())
        if found["kind"] != "prose":
            continue
        if denials.match(found.get("text", "")):
            wrong.append((url, found["text"]))

    assert not wrong, (
        f"{len(wrong)} page(s) whose prerequisite field is a denial are "
        f"counted as stating a prerequisite:\n"
        + "\n".join(f"  {u}: {t!r}" for u, t in wrong[:5]))


@needs_cache
def test_the_classifier_finds_the_prerequisites_the_district_publishes():
    """A classifier that found NOTHING would pass both tests above by
    agreeing with an empty set. PWCS is the district that uses the typed
    field; if this drops to zero the corpus or the pattern has moved."""
    typed = sum(1 for _, markup in course_pages()
                if course_page.classify(markup, set())["kind"] == "typed")
    assert typed > 50, (
        f"only {typed} cached PWCS pages carry a typed prerequisite; the "
        f"pattern or the corpus has changed and every figure resting on it "
        f"is now suspect")


def test_the_recorded_classification_covers_the_corpus_the_page_quotes():
    """**This file's three other tests skip in a fresh clone**, because
    `data/` is gitignored — so the claim "961 cached PWCS pages, 0 classified
    differently" rested on a corpus nobody else has, in the guard most likely
    to catch a reader regression. It did not catch two of them.

    `docs/sources/pwcs-classification-measured.json` is what a reader without
    the cache can check: every page's path, a hash of its markup, and what
    `classify` answered. The markup is NOT stored — it is the district's
    course text and this repo does not republish it.

    This test needs no cache and so cannot skip.
    """
    import json

    record = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "sources"
              / "pwcs-classification-measured.json")
    assert record.exists(), (
        "the corpus claim has no committed artefact; run "
        "`python -m etl.probe_pwcs_classification --record`")
    found = json.loads(record.read_text(encoding="utf-8"))
    assert found["pages"] > 900, found["pages"]
    assert sum(found["kinds"].values()) == found["pages"]
    assert set(found["digest_by_kind"]) == set(found["kinds"])
    assert len(found["digest"]) == 64


@needs_cache
def test_the_classifier_still_says_what_the_record_says():
    """The regression the corpus is for, made checkable rather than narrated.

    A drift here is either the reader changing or the page changing, and the
    stored hash is what tells them apart — which is the whole reason the hash
    is stored alongside the answer.
    """
    import json

    record = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "sources"
              / "pwcs-classification-measured.json")
    found = json.loads(record.read_text(encoding="utf-8"))
    pages = {url[len(BASE):] if url.startswith(BASE) else url: markup
             for url, markup in course_pages()}
    published = set(pages)

    by_kind = {}
    every = hashlib.sha256()
    for path, markup in sorted(pages.items()):
        now = course_page.classify(markup, published, BASE)
        line = (f"{path}\t{hashlib.sha256(markup.encode()).hexdigest()}\t"
                f"{now['kind']}\t{','.join(now.get('links') or [])}")
        every.update(line.encode())
        by_kind.setdefault(now["kind"], []).append(line)

    if every.hexdigest() == found["digest"]:
        return
    # A drift. Say WHICH answer moved — the per-kind digests are there so
    # this does not have to be "something changed".
    now_by_kind = {kind: hashlib.sha256("".join(lines).encode()).hexdigest()
                   for kind, lines in sorted(by_kind.items())}
    moved = sorted(set(now_by_kind.items()) ^ set(found["digest_by_kind"].items()))
    pytest.fail(
        f"the corpus classification no longer matches the record. Either the "
        f"reader changed or the cached pages did — the markup hashes are "
        f"inside the digest, so re-record only after checking which. Kinds "
        f"that moved: {sorted({kind for kind, _ in moved})}")
