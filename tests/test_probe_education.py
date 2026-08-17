"""The probe's guards, tested without a network.

This script produces every source figure quoted in this repo, so the failure
that matters is not "it crashed" — it is "it printed a number that was not a
measurement". Each test below is about one way that could happen.
"""

import json
import urllib.error

import pytest

from etl import probe_education as probe


def test_a_normal_response_yields_its_count():
    assert probe.total({"count": 9_026_310, "results": []}, "IPEDS") == 9_026_310


def test_zero_is_refused_rather_than_published():
    """A wrong year or a renamed dataset answers 200 with `count: 0`. A table
    row reading 0 looks like a measurement when it is a broken request."""
    with pytest.raises(ValueError, match="refusing to publish"):
        probe.total({"count": 0, "results": []}, "CCD schools")


def test_a_missing_count_field_is_refused():
    """If the API shape changes, saying so beats inventing a number."""
    with pytest.raises(ValueError, match="no `count`"):
        probe.total({"results": []}, "IPEDS")


@pytest.mark.parametrize("value", ["9026310", None, 9026310.0, [1]])
def test_a_count_that_is_not_an_integer_is_refused(value):
    with pytest.raises(ValueError, match="not an integer"):
        probe.total({"count": value}, "IPEDS")


def test_every_source_path_carries_the_year(monkeypatch):
    """The year is substituted into the path, so a source that ignored it would
    silently be counted for the wrong year while the header said otherwise."""
    for _, path, _ in probe.SOURCES:
        assert "{year}" in path, path


def test_probe_asks_for_the_year_it_was_given(monkeypatch):
    asked = []
    monkeypatch.setattr(probe, "fetch", lambda p: asked.append(p) or {"count": 1})
    probe.probe(2019)
    assert asked, "no request was made"
    assert all("/2019/" in p for p in asked), asked


def test_a_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda s: None)
    attempts = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"count": 5}'

    def flaky(*a, **k):
        attempts.append(1)
        if len(attempts) < 3:
            import io
            raise urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b""))
        return Response()

    monkeypatch.setattr(probe.urllib.request, "urlopen", flaky)
    assert probe.fetch("x/")["count"] == 5
    assert len(attempts) == 3


def test_a_404_is_not_retried_and_names_the_url(monkeypatch):
    """Unlike the openFDA probe, a 404 here is not an empty answer — it means
    the dataset or year does not exist, which is about the request."""
    monkeypatch.setattr(probe.time, "sleep", lambda s: None)
    attempts = []

    def missing(*a, **k):
        import io
        attempts.append(1)
        raise urllib.error.HTTPError("u", 404, "nope", {}, io.BytesIO(b""))

    monkeypatch.setattr(probe.urllib.request, "urlopen", missing)
    with pytest.raises(RuntimeError, match="404"):
        probe.fetch("college-university/ipeds/directory/1066/")
    assert len(attempts) == 1, f"a 404 was retried {len(attempts)} times"


def test_a_non_json_body_is_reported_as_such(monkeypatch):
    """A proxy returning an HTML error page. Reporting it as 'not JSON' beats a
    traceback that reads like a bug in this script."""
    class Html:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"<html>502</html>"

    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: Html())
    with pytest.raises(RuntimeError, match="not JSON"):
        probe.fetch("x/")


def test_an_implausible_year_is_refused(capsys):
    assert probe.main(["--year", "1066"]) == 1
    assert "plausible" in capsys.readouterr().err


def test_a_refusal_exits_1_and_an_outage_exits_2(monkeypatch, capsys):
    """Two different failures that must not look alike: our data is wrong
    versus their server is down."""
    monkeypatch.setattr(probe, "probe",
                        lambda y, quiet=False: (_ for _ in ()).throw(ValueError("reported 0 records")))
    assert probe.main([]) == 1
    assert "refused" in capsys.readouterr().err

    monkeypatch.setattr(probe, "probe",
                        lambda y, quiet=False: (_ for _ in ()).throw(RuntimeError("unreachable")))
    assert probe.main([]) == 2
    assert "unreachable" in capsys.readouterr().err


def test_json_output_is_machine_readable(monkeypatch, capsys):
    """The docs pull figures from this, so it has to parse and carry the date."""
    monkeypatch.setattr(probe, "fetch", lambda p: {"count": 7})
    assert probe.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["year"] == 2022
    assert payload["retrieved_at"].endswith("+00:00")
    assert len(payload["sources"]) == len(probe.SOURCES)
    assert all(s["count"] == 7 for s in payload["sources"])


def test_sources_we_cannot_probe_are_named_not_omitted():
    """The CIP-SOC crosswalk is the join the whole graph rests on and it is not
    in this table. Silence would read as absence."""
    names = [n for n, _, _ in probe.UNPROBED]
    assert any("CIP-SOC" in n for n in names), names
    assert any("O*NET" in n for n in names), names
