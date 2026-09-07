"""How the Registry is read — paging, and the honesty of the sample.

Split out of `tests/test_probe_registry.py` for #86: that file sat at 529 lines,
over the review limit, so every review skipped it whole — and it was the file
asserting the findings the Registry pages rest on.

Split by SUBJECT rather than by length. These cases fix which pages get READ,
and what the probe is allowed to say about how it chose them. What is found on
those pages is `test_probe_registry.py`; the command line is
`test_registry_cli.py`.

The description matters as much as the sampling. A walk that reads 12 of 958
pages and calls itself a reading of the Registry is the failure these cases
exist to prevent: it has to say what it skipped.
"""

import re

import pytest

from etl import registry_read as read


def test_pages_are_spread_across_the_population_not_taken_from_the_head():
    """Reading pages 1..12 samples whatever sorts first, which one publisher's
    bulk upload can dominate. Spreading them changed the measured rate from
    83/600 to 150/600 — the concern was real."""
    population = 47861
    wanted = 600
    pages, size = read.sample_pages(wanted, population)
    total_pages = -(-population // read.PER_PAGE)

    assert pages[0] == 1
    assert len(pages) == len(set(pages)) == -(-wanted // read.PER_PAGE)
    # Derived from the constants rather than hard-coded, so changing PER_PAGE
    # does not silently turn this into a test of nothing.
    assert pages[-1] > total_pages * 0.8, "does not reach the far end"
    assert size == read.PER_PAGE


def described(wanted: int, population: int | None) -> str:
    """The string the probe actually prints, for a walk that read every page it
    planned. Pointed at `describe()`, because that is the live implementation —
    these guards used to assert on a string `sample_pages` returned and nobody
    printed, so both retired claims could be reintroduced through a green
    suite."""
    pages, size = read.sample_pages(wanted, population)
    return read.describe(pages, size, population)


@pytest.mark.parametrize("population", [None, 0, 100, 47861])
def test_the_sampling_description_never_claims_randomness(population):
    """Stripping the literal "not random" would also hide "not randomly-ish".
    Asserting on the whole clause is what actually pins the claim."""
    how = described(600, population)
    for match in re.finditer(r"\brandom\w*", how):
        prefix = how[max(0, match.start() - 4):match.start()]
        assert prefix.endswith("not "), f"claims randomness: {how}"


def test_a_population_smaller_than_the_sample_reads_everything():
    pages, _ = read.sample_pages(600, 120)
    assert pages == [1, 2, 3]
    assert "whole population, not a sample" in described(600, 120)


def test_an_unknown_population_falls_back_and_says_so():
    """If x-total is missing the pages cannot be spread. That is a weaker
    sample and the description has to admit it rather than look identical."""
    pages, _ = read.sample_pages(600, None)
    assert pages == list(range(1, 13))
    how = described(600, None)
    assert "population unknown" in how and "biased" in how


def test_a_truncated_walk_with_an_unknown_population_is_described(monkeypatch):
    """Both weaknesses at once: the cap ended the walk early AND the population
    is unknown, so the description can claim neither a reach nor a spread. The
    branch existed and nothing exercised it."""
    how = read.describe([1, 2], read.PER_PAGE, None)
    assert "population unknown" in how
    assert "biased" in how
    for match in re.finditer(r"\brandom\w*", how):
        assert how[max(0, match.start() - 4):match.start()].endswith("not ")


def test_a_walk_that_read_nothing_says_so():
    assert read.describe([], read.PER_PAGE, 47861) == "nothing was read"


def test_the_sampling_description_does_not_claim_the_tail_it_skips():
    """Stride 79 over 12 pages reaches page 870 of 958. Saying "spread across
    all 958 pages" claimed 88 pages — about 4,400 courses — that are never read."""
    population = 47861
    pages, _ = read.sample_pages(600, population)
    how = described(600, population)
    total_pages = -(-population // read.PER_PAGE)
    assert pages[-1] < total_pages, "the stride does reach the end after all"
    assert f"{pages[0]}-{pages[-1]}" in how
    assert f"{total_pages:,}" in how
    assert "not sampled" in how
    assert f"all {total_pages:,} pages" not in how


def test_a_sample_that_is_not_a_multiple_of_a_page_is_not_short_changed():
    """`--courses 130` asked for three pages' worth and got two, silently
    sampling 100 while reporting the request. Ceiling, not floor."""
    pages, _ = read.sample_pages(130, 47861)
    assert len(pages) == 3


# --------------------------------------------------------------------------
# what the description is allowed to claim — from the #89 review
# --------------------------------------------------------------------------

def test_reading_every_page_at_a_short_size_is_not_the_whole_population():
    """`total_pages` is derived from PER_PAGE, so "read every page" and "read
    every record" are different claims whenever the page size is short.

    At population 10 with a size of 5, one page IS every page by count and half
    the records by content — and this said "the whole population, not a
    sample". Overclaiming coverage is the one thing this module exists to
    prevent; a caveat that overstates reach is worse than no caveat, because it
    is quoted.

    Reachable, not hypothetical: `sample_pages(5, 10)` returns exactly that.
    """
    pages, size = read.sample_pages(5, 10)
    assert size < read.PER_PAGE, "the short-page case is unreachable, so this proves nothing"

    said = read.describe(pages, size, 10)
    # The CLAIM, not the phrase. "whole population" also appears in the
    # corrected wording, as "this is not the whole population" — asserting on
    # the bare phrase would fail on the fix and pass on a reworded bug.
    assert "is the whole population, not a sample" not in said, said
    assert "5 of 10 records" in said, said
    assert "not the whole population" in said, said


def test_reading_every_page_at_a_full_size_still_says_whole_population():
    """The honest complete case must keep saying so — a fix that made every
    description hedge would be its own inaccuracy."""
    said = read.describe([1, 2], read.PER_PAGE, 100)
    assert "whole population" in said, said


def test_the_total_signature_does_not_promise_a_None_it_never_returns():
    """`int | str | None` named a third case that cannot happen: every path
    returns an int or one of four strings. A caller writing `if result is None`
    is writing dead code the annotation told them to write."""
    import inspect
    assert "None" not in str(inspect.signature(read.total).return_annotation)


def test_get_and_head_are_separate_because_their_return_types_are():
    """One function returned bytes or a header object depending on a boolean,
    so its signature could describe neither and carried no annotation at all.

    Split, and asserted here rather than left to review: the boolean is the
    kind of thing that gets reintroduced as a convenience.
    """
    import inspect
    assert inspect.signature(read.get).return_annotation is bytes or \
        "bytes" in str(inspect.signature(read.get).return_annotation)
    assert "Message" in str(inspect.signature(read.head).return_annotation)
    for name in ("get", "head"):
        params = inspect.signature(getattr(read, name)).parameters
        assert list(params) == ["url"], (
            f"{name}{tuple(params)} takes more than a url — a flag that changes "
            f"the return type is what was just removed")


# --- transport is retried, a status code is not -----------------------------

def test_a_truncated_body_is_retried_rather_than_escaping(monkeypatch):
    """`IncompleteRead` is an `http.client.HTTPException`, which was not in the
    caught tuple — so a body that stopped early escaped as a bare exception
    while every other failure on this path arrived as `HttpStatus`. The
    958-page sweep for #58 hit one at page 75, twenty minutes in."""
    import http.client
    import urllib.request

    calls = []

    class Response:
        def __enter__(self):
            calls.append(1)
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            # Raised from read(), NOT from __enter__. The failure this guards is
            # a body that stops MID-READ — the sweep got 36,665 of 191,520
            # bytes. Raising on entry never reaches `extract`, so it would have
            # passed even with the read left outside the try, which is the one
            # thing the docstring above `_request` says must not happen.
            if len(calls) < 3:
                raise http.client.IncompleteRead(b"partial", 191520)
            return b"whole"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Response())
    monkeypatch.setattr(read.time, "sleep", lambda _: None)
    assert read.get("https://example.test/x") == b"whole"
    assert len(calls) == 3, "it should retry twice before succeeding"


def test_a_status_code_is_not_retried(monkeypatch):
    """An HTTPError is the service answering. Asking again gets the same
    answer, and retrying a 403 is just three 403s."""
    import urllib.error
    import urllib.request

    calls = []

    def refuse(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("https://example.test/x", 403, "no", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(read.time, "sleep", lambda _: None)
    with pytest.raises(read.HttpStatus):
        read.get("https://example.test/x")
    assert len(calls) == 1, "a status code must not be retried"
