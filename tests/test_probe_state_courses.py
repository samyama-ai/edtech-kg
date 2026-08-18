"""The state-courses probe, tested without a network.

The figures this produces are the whole substance of #40's conclusion, so the
failure that matters is the same as in the other probes: reporting a number that
was not a measurement.
"""

import csv
import io
import zipfile

import pytest

from etl import probe_state_courses as probe


def csv_bytes(rows):
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue().encode()


def test_texas_does_not_count_the_header_as_a_course(monkeypatch):
    """The bug this test exists for: an earlier draft reported 1,636 courses
    when the file has 1,635 plus a header."""
    monkeypatch.setattr(probe, "fetch", lambda url, expect=None: csv_bytes([
        ["Code", "Translation", "Subject"],
        ["01010000", "Pre-Kindergarten", "x"],
        ["01020000", "Kindergarten", "y"],
    ]))
    r = probe.texas()
    assert r["courses"] == 2, "the header row was counted as a course"
    assert r["fields"][0] == "Code"


def test_texas_reports_prerequisite_terms_it_finds(monkeypatch):
    monkeypatch.setattr(probe, "fetch", lambda url, expect=None: csv_bytes([
        ["Code", "Translation"],
        ["1", "Algebra 2 — prerequisite: Algebra 1"],
    ]))
    assert probe.texas()["prerequisite_terms"]["prerequisit"] == 1


def test_an_empty_source_is_refused_rather_than_counted_as_zero(monkeypatch):
    """A moved file or a bad response would otherwise report 0 courses, which
    reads as a measurement of a state with no courses."""
    monkeypatch.setattr(probe, "fetch", lambda url, expect=None: csv_bytes([["Code"]]))
    with pytest.raises(ValueError, match="refusing"):
        probe.texas()


def test_a_non_workbook_response_is_refused(monkeypatch):
    """Exercises the real fetch(), not a stub of it — an HTML error page saved
    as an .xlsx would otherwise fail much later and much less clearly."""
    class Html:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"<html>404 Not Found</html>"

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Html())
    with pytest.raises(ValueError, match="expected format"):
        probe.fetch("https://example.invalid/x.xlsx", expect=b"PK")


def test_a_response_of_the_right_shape_passes(monkeypatch):
    class Zip:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"PK\x03\x04rest"

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Zip())
    assert probe.fetch("https://example.invalid/x.xlsx", expect=b"PK").startswith(b"PK")


def test_an_http_error_names_the_url(monkeypatch):
    import urllib.error, io
    monkeypatch.setattr(probe.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.HTTPError("u", 403, "no", {}, io.BytesIO(b""))))
    with pytest.raises(RuntimeError, match="403"):
        probe.fetch("https://example.invalid/x")


def test_a_blocked_state_is_named_not_omitted():
    """Florida, Virginia and California are absent from the measured table.
    Silence would read as 'these states publish nothing'."""
    states = [s for s, _, _ in probe.BLOCKED]
    assert states == ["Florida", "Virginia", "California"]
    assert all(u.startswith("https://") for _, u, _ in probe.BLOCKED)


def test_the_prerequisite_terms_cover_more_than_the_obvious_word():
    """A state could state a requirement without using the word."""
    for term in ("prerequisit", "must have completed", "before taking"):
        assert term in probe.PREREQ_TERMS


def test_json_output_carries_both_measured_and_blocked(monkeypatch, capsys):
    import json
    monkeypatch.setattr(probe, "texas", lambda: {"state": "Texas", "courses": 1,
                                                 "format": "CSV", "prerequisite_terms": {}})
    monkeypatch.setattr(probe, "new_york", lambda: {"state": "New York", "courses": 2,
                                                    "format": "XLSX", "prerequisite_terms": {}})
    assert probe.main(["--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert len(d["measured"]) == 2 and len(d["blocked"]) == 3
    assert d["retrieved_at"].endswith("+00:00")
