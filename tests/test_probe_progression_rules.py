"""The progression-rules probe, driven without the network.

The finding is that a column FLAGS coursework rather than NAMING it, so the
one thing that must be right is the distinction between those two. It was
wrong first: an unbounded `unit` matched `unitid` and the probe reported a
column naming a college as a column naming a course — this finding inverted.
"""

from __future__ import annotations

import json

import pytest

from etl import probe_progression_rules as probe


def test_a_column_naming_a_college_is_not_a_column_naming_a_course():
    """**The false positive that would have inverted the finding.** `unitid`
    is the institution key; an unbounded `unit` matched it."""
    assert probe.names_coursework("unitid") is False
    assert probe.names_coursework("fips") is False
    assert probe.names_coursework("reqt_college_prep") is False, (
        "a flag ABOUT coursework is not a column naming it — that is the "
        "distinction this whole page rests on")


def test_a_column_that_really_names_coursework_is_found():
    """The negative must be reachable only by looking. A rule that matched
    nothing would make "0 fields name a course" true of any input."""
    for field in ("course_credits", "subject_area", "cip_code",
                  "required_courses", "credit_units"):
        assert probe.names_coursework(field) is True, field


def test_an_underscore_does_not_hide_a_token():
    """`\\b` does not fix the substring problem: `_` is a word character, so
    `\\bcourse\\b` misses a real `course_credits`. Tokens are split on
    non-alphanumerics and compared."""
    assert probe.names_coursework("course_credits") is True
    assert probe.names_coursework("min_credits_required") is True


def test_a_scalar_count_of_years_is_not_coursework():
    """`years_college_reqd` carries a number of years, not a course."""
    assert probe.names_coursework("years_college_reqd") is False


def test_a_short_page_is_refused_rather_than_counted(monkeypatch):
    """"6,138 institutions and not one named course" is national only if
    every institution was asked."""
    monkeypatch.setattr(probe, "fetch", lambda url: (
        200, json.dumps({"count": 6138, "results": [{"unitid": 1}]})))
    with pytest.raises(probe.Unreachable, match="6138"):
        probe.admission_rules()


def test_a_refusal_from_ipeds_stops_the_run(monkeypatch):
    monkeypatch.setattr(probe, "fetch", lambda url: (503, ""))
    with pytest.raises(probe.Unreachable, match="503"):
        probe.admission_rules()


def test_a_refusal_elsewhere_is_recorded_rather_than_raised(monkeypatch):
    """A 403 from ECS is the finding for Q57. It has to come back as data."""
    monkeypatch.setattr(probe, "fetch", lambda url: (403, ""))
    found = probe.published_as_prose()
    for sources in found.values():
        for entry in sources.values():
            assert entry["status"] == 403
            assert entry["is_json"] is False


def test_q93_is_read_from_the_other_record(monkeypatch, tmp_path):
    """Read, not re-measured — two probes measuring one fact is two figures
    that can disagree."""
    other = tmp_path / "articulation-measured.json"
    other.write_text(json.dumps({
        "retrieved_at": "2026-09-08",
        "course_level": {"searched": 129, "matched": []},
        "institution_level": {"flags": {"ap_credit": {}, "dual_credit": {}}},
    }), encoding="utf-8")
    monkeypatch.setattr(probe, "ARTICULATION", other)
    found = probe.articulation_from_the_record()
    assert found["available"] is True
    assert found["endpoints_searched"] == 129
    assert found["endpoints_naming_a_course_level_rule"] == 0
    assert found["institution_level_flags"] == ["ap_credit", "dual_credit"]


def test_a_missing_articulation_record_says_so(monkeypatch, tmp_path):
    """Rather than reporting a zero that was never measured."""
    monkeypatch.setattr(probe, "ARTICULATION", tmp_path / "absent.json")
    found = probe.articulation_from_the_record()
    assert found["available"] is False
    assert "probe_articulation" in found["note"]
