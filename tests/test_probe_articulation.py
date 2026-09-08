"""The articulation probe's arithmetic, driven without the network.

Two things decide the finding: whether a flag's counts are divided by the
institutions that ANSWERED rather than by the population, and whether an
endpoint search that matches nothing did so by looking.
"""

from __future__ import annotations

import pytest

from etl import probe_articulation as probe


class Fake:
    """Answers from a script, so a test can drive the probe's arithmetic."""

    def __init__(self, answers):
        self.answers = answers

    def __call__(self, url):
        for fragment, body in self.answers.items():
            if fragment in url:
                return body
        raise AssertionError(f"no scripted answer for {url}")


def test_a_missing_answer_is_not_a_refusal(monkeypatch):
    """IPEDS codes "not reported" as -1 and "not applicable" as -2. Folding
    those into the zeroes would report an institution that was never asked as
    one that declines to grant credit — and the share is the headline."""
    rows = ([{"ap_credit": 1}] * 6 + [{"ap_credit": 0}] * 2
            + [{"ap_credit": -1}, {"ap_credit": -2}])
    monkeypatch.setattr(probe, "get", Fake({
        "institutional-characteristics": {"count": 10, "results": rows}}))
    found = probe.institution_flags()["flags"]["ap_credit"]
    assert found["grants"] == 6
    assert found["does_not"] == 2
    assert found["answered"] == 8
    assert found["missing"] == {"not reported": 1, "not applicable": 1}
    # 6/8, not 6/10. Dividing by the population would say 60%.
    assert found["percent_of_answered"] == 75.0


def test_a_short_page_is_refused_rather_than_counted(monkeypatch):
    """"3,240 institutions grant AP credit" is a national figure only if every
    institution was asked. A page returning fewer rows than the API's own
    count would understate every flag on the page."""
    monkeypatch.setattr(probe, "get", Fake({
        "institutional-characteristics": {"count": 6138,
                                          "results": [{"ap_credit": 1}]}}))
    with pytest.raises(probe.Unreachable, match="6138"):
        probe.institution_flags()


def test_a_missing_count_is_refused(monkeypatch):
    monkeypatch.setattr(probe, "get", Fake({
        "institutional-characteristics": {"results": [{"ap_credit": 1}]}}))
    with pytest.raises(probe.Unreachable, match="without a count"):
        probe.institution_flags()


def test_an_empty_endpoint_list_is_refused(monkeypatch):
    """**The zero is the finding**, so it must not be reachable by not
    looking. An endpoint list that came back empty would make
    "0 of 0 endpoints mention articulation" true and meaningless."""
    monkeypatch.setattr(probe, "get", Fake({"api-endpoints": {"results": []}}))
    with pytest.raises(probe.Unreachable, match="by not looking"):
        probe.measure()


def test_the_course_level_search_reads_url_and_description():
    """An endpoint whose URL says nothing may still describe itself as
    carrying articulation, and vice versa. Searching one field would report a
    no that was never asked of the other."""
    found = probe.course_level_sources([
        {"endpoint_url": "/api/v1/x/articulation/", "description": ""},
        {"endpoint_url": "/api/v1/y/", "description": "Course equivalency"},
        {"endpoint_url": "/api/v1/z/", "description": "Enrollment counts"},
    ])
    assert found["searched"] == 3
    assert [m["endpoint"] for m in found["matched"]] == [
        "/api/v1/x/articulation/", "/api/v1/y/"]


def test_the_flags_are_named_not_discovered():
    """A probe reporting whatever matched "credit" would change its own
    subject when the API adds a field, and the page's four rows would silently
    become five."""
    assert probe.CREDIT_FLAGS == ("ap_credit", "dual_credit",
                                  "credit_for_life",
                                  "military_training_credit")
