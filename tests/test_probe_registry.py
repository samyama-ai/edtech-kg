"""Tests for the Credential Registry probe.

The network is stubbed throughout. Under test: the two-totals reconciliation
(#59), the sampling method the review of #57 asked to be made explicit, and the
refusals.
"""

import io
import json
import urllib.error

import pytest

from etl import probe_registry as probe


def stub(monkeypatch, payload: bytes, x_total: int | None = None):
    class R:
        headers = {"x-total": str(x_total)} if x_total is not None else {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return payload
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())


# --------------------------------------------------------------------------
# how the sample is chosen — the review of #57 called this under-specified
# --------------------------------------------------------------------------

def test_pages_are_spread_across_the_population_not_taken_from_the_head():
    """Reading pages 1..12 samples whatever sorts first, which one publisher's
    bulk upload can dominate. Spreading them changed the measured rate from
    83/600 to 150/600 — the concern was real."""
    pages, how = probe.sample_pages(600, 47861)
    assert pages[0] == 1 and len(pages) == 12
    assert pages[-1] > 800                      # reaches the far end
    assert len(set(pages)) == 12                # no page read twice
    assert "stride" in how and "not random" in how


def test_the_sampling_description_never_claims_randomness():
    for population in (None, 0, 100, 47861):
        assert "random" not in probe.sample_pages(600, population)[1].replace(
            "not random", "")


def test_a_population_smaller_than_the_sample_reads_everything():
    pages, how = probe.sample_pages(600, 120)
    assert pages == [1, 2, 3]
    assert "whole population, not a sample" in how


def test_an_unknown_population_falls_back_and_says_so():
    """If x-total is missing the pages cannot be spread. That is a weaker
    sample and the description has to admit it rather than look identical."""
    pages, how = probe.sample_pages(600, None)
    assert pages == list(range(1, 13))
    assert "population unknown" in how and "biased" in how


def test_the_publisher_spread_is_reported(monkeypatch):
    """A verdict drawn from a sample that turns out to be three publishers is a
    fact about those three."""
    stub(monkeypatch, json.dumps([
        {"published_by": "org/a", "decoded_resource": {"@type": "ceterms:Course"}},
        {"published_by": "org/a", "decoded_resource": {"@type": "ceterms:Course"}},
        {"published_by": "org/b", "decoded_resource": {"@type": "ceterms:Course"}},
    ]).encode(), x_total=150)
    assert probe.course_prerequisites(sample=50)["distinct_publishers"] == 2


# --------------------------------------------------------------------------
# prerequisites in published courses — the number the probe exists for
# --------------------------------------------------------------------------

def course(**extra):
    return {"decoded_resource": {"@type": "ceterms:Course", **extra}}


def test_a_free_text_condition_is_not_counted_as_resolvable(monkeypatch):
    """"PSYC101" is a string. Resolving it means guessing which catalogue it
    belongs to, so it is counted as stated-but-not-resolvable."""
    body = json.dumps([course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:description": {"en-US": "PSYC101"}}]})]).encode()
    stub(monkeypatch, body)
    r = probe.course_prerequisites(sample=50)
    assert r["stating_a_prerequisite"] == 1
    assert r["resolvable"] == 0
    assert r["free_text_only"] == 1
    assert r["examples"] == ["PSYC101"]


def test_a_targeted_condition_counts_as_resolvable(monkeypatch):
    body = json.dumps([course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Prerequisites"},
         "ceterms:targetLearningOpportunity": [{"@id": "https://x/course/1"}]}]})]).encode()
    stub(monkeypatch, body)
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"], r["free_text_only"]) == (1, 1, 0)


def test_the_typed_property_counts_as_resolvable(monkeypatch):
    stub(monkeypatch, json.dumps([course(**{
        "ceterms:prerequisite": [{"@id": "https://x/course/2"}]})]).encode())
    r = probe.course_prerequisites(sample=50)
    assert (r["stating_a_prerequisite"], r["resolvable"]) == (1, 1)


def test_a_condition_that_is_not_a_prerequisite_is_not_counted(monkeypatch):
    """Courses carry `ceterms:requires` for co-requisites, residency and fees.
    Counting all of them would overstate the rate."""
    stub(monkeypatch, json.dumps([course(**{"ceterms:requires": [
        {"ceterms:name": {"en-US": "Residency requirement"},
         "ceterms:description": {"en-US": "Must live in-district"}}]})]).encode())
    r = probe.course_prerequisites(sample=50)
    assert r["courses_sampled"] == 1 and r["stating_a_prerequisite"] == 0


def test_non_course_records_are_not_counted_in_the_denominator(monkeypatch):
    stub(monkeypatch, json.dumps([
        course(), {"decoded_resource": {"@type": "ceterms:Credential"}}]).encode())
    assert probe.course_prerequisites(sample=50)["courses_sampled"] == 1


def test_zero_courses_is_refused_rather_than_reported_as_a_rate(monkeypatch):
    """A rate over an empty sample is not a finding — the same refusal the
    education and state-course probes make."""
    stub(monkeypatch, b"[]")
    with pytest.raises(ValueError, match="refusing"):
        probe.course_prerequisites(sample=50)


