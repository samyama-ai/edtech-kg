"""What the enrolment probe reports, without touching the network.

`fetch` is stubbed in every test here, so nothing below reaches the Urban
wrapper and none of it re-runs the live measurement — that lives in
`docs/sources/enrolment-measured.json`.

Two of these exist because the page makes promises about them. The doc says the
probe walks past a level that answers empty, and it says the finding flips on
its own if enrolment ever grows a CIP field. A promise nothing tests is a
promise the next reader has to take on trust.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from etl import probe_enrolment as probe

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "sources" / "enrolment-measured.json"

ENROLMENT_ROW = {"unitid": 100654, "year": 2022, "level_of_study": 1,
                 "enrollment_fall": 300, "race": 1, "sex": 1}
COMPLETIONS_ROW = {"unitid": 100654, "year": 2022, "cipcode_6digit": "110701",
                   "awards_6digit": 12, "award_level": 5}


def stub(monkeypatch, answers: dict) -> list[str]:
    """Answer `fetch` from a dict keyed by substring; record what was asked."""
    asked: list[str] = []

    def fake_fetch(path: str) -> dict:
        asked.append(path)
        for needle, payload in answers.items():
            if needle in path:
                return payload
        return {"count": 0, "results": []}

    monkeypatch.setattr(probe, "fetch", fake_fetch)
    return asked


def page(count: int, row: dict | None) -> dict:
    return {"count": count, "results": [row] if row else []}


def test_it_walks_past_a_level_that_answers_empty(monkeypatch):
    """The bug the design exists for: one endpoint is empty at level 99 and
    populated at the others, so a probe that asked only 99 would record a
    populated source as having no rows.
    """
    asked = stub(monkeypatch, {"/2022/99/": page(0, None),
                               "/2022/1/": page(5959, ENROLMENT_ROW)})

    measured = probe.read_endpoint(
        "fte", "college-university/ipeds/enrollment-full-time-equivalent/"
               "{year}/{level}/", 2022)

    assert measured["rows_at_fields_from"] == 5959, (
        "the populated level was not reached")
    assert measured["fields_seen"] is True
    assert measured["fields_from"].endswith("/2022/1/")
    assert [attempt["rows"] for attempt in measured["levels"]][:2] == [0, 5959]
    assert len(asked) == len(probe.LEVELS), (
        "every level must be requested — a per-level count in the record that "
        "was never asked for is an assertion, not a measurement")


def test_an_empty_endpoint_records_no_synthesised_path(monkeypatch):
    """A path in the record is a URL a reader can paste, or it is absent.

    The first version joined the tried levels into one string, producing
    `.../enrollment-headcount/2022/99/1/2/3/` — a URL that was never requested
    and answers 404 to anyone checking it.
    """
    stub(monkeypatch, {})  # every level empty

    measured = probe.read_endpoint(
        "headcount",
        "college-university/ipeds/enrollment-headcount/{year}/{level}/", 2022)

    assert measured["fields_from"] is None
    assert measured["rows_at_fields_from"] == 0
    assert measured["fields_seen"] is False, (
        "an endpoint that returned nothing must not read as evidence")
    assert measured["paths_tried"] == [
        f"college-university/ipeds/enrollment-headcount/2022/{level}/"
        for level in probe.LEVELS]
    for path in measured["paths_tried"]:
        assert path.count("/2022/") == 1 and "/1/2/3/" not in path


def test_the_finding_flips_when_enrolment_grows_a_cip_field(monkeypatch):
    """The doc promises "if enrolment ever grows a CIP field it flips and #204
    reopens". This is that promise, held to.
    """
    with_cip = dict(ENROLMENT_ROW, cipcode_6digit="110701")
    stub(monkeypatch, {"fall-enrollment": page(10, with_cip),
                       "completions-cip-6": page(9, COMPLETIONS_ROW),
                       "api-endpoints": {"count": 1, "results": [
                           {"endpoint_url": "/api/v1/x/completions-cip-6/"}]}})

    measured = probe.measure(2022)

    assert measured["enrolment_is_by_programme"] is True
    assert "answerable" in measured["finding"]


def test_the_finding_holds_when_no_enrolment_endpoint_carries_cip(monkeypatch):
    stub(monkeypatch, {"fall-enrollment": page(10, ENROLMENT_ROW),
                       "completions-cip-6": page(9, COMPLETIONS_ROW),
                       "api-endpoints": {"count": 1, "results": [
                           {"endpoint_url": "/api/v1/x/completions-cip-6/"}]}})

    measured = probe.measure(2022)

    assert measured["enrolment_is_by_programme"] is False
    assert "cannot be compared" in measured["finding"]


def test_a_truncated_catalogue_is_refused(monkeypatch):
    """The negative claim rests on having seen the whole list. A page that
    reports more entries than it returned would keep reporting the same paths
    from a list that had been cut, with nothing to say so.
    """
    stub(monkeypatch, {"api-endpoints": {
        "count": 400,
        "results": [{"endpoint_url": "/api/v1/x/completions-cip-6/"}]}})

    with pytest.raises(probe.Refused, match="truncated"):
        probe.cip_endpoints()


def test_a_missing_count_is_refused(monkeypatch):
    """No `count` means the API shape changed; a probe that reads on regardless
    publishes figures it cannot vouch for.
    """
    stub(monkeypatch, {"fall-enrollment": {"results": [ENROLMENT_ROW]}})

    with pytest.raises(probe.Refused, match="no `count`"):
        probe.read_endpoint(
            "fall", "college-university/ipeds/fall-enrollment/{year}/"
                    "{level}/race/sex/", 2022)


def test_the_committed_record_says_what_the_page_says():
    """The record is the evidence behind `docs/sources/enrolment.md`. If it ever
    reports enrolment as comparable, the page is wrong and #204 is open again.
    """
    record = json.loads(RECORD.read_text(encoding="utf-8"))

    assert record["enrolment_is_by_programme"] is False
    assert record["completions"]["cip_fields"] == ["cipcode_6digit"]
    for source in record["enrolment"]:
        assert source["cip_fields"] == [], (
            f"{source['endpoint']} carries {source['cip_fields']}; the page "
            f"claims no enrolment endpoint does")
        for attempt in source["levels"]:
            assert "/1/2/3/" not in attempt["path"], (
                "a synthesised path is back in the record")


def test_a_level_the_endpoint_does_not_publish_is_recorded_not_fatal(monkeypatch):
    """A 404 on one level means "this endpoint does not publish that level or
    year". Aborting on it would discard every successful request before it.
    """
    def fake_fetch(path: str) -> dict:
        if "/2022/99/" in path:
            raise RuntimeError(f"404 on https://example/{path}")
        return page(7, ENROLMENT_ROW)

    monkeypatch.setattr(probe, "fetch", fake_fetch)

    measured = probe.read_endpoint(
        "fte", "college-university/ipeds/x/{year}/{level}/", 2022)

    assert measured["levels"][0] == {
        "level": 99, "path": "college-university/ipeds/x/2022/99/",
        "rows": None, "http": 404}
    assert measured["rows_at_fields_from"] == 7, "the later levels were skipped"
    assert measured["fields_seen"] is True


def test_any_other_http_error_still_fails_loudly(monkeypatch):
    """Only a 404 is an answer. A 500 is the API breaking, and a probe that
    treats it as data publishes a finding it cannot stand behind.
    """
    def fake_fetch(path: str) -> dict:
        raise RuntimeError(f"500 on https://example/{path}")

    monkeypatch.setattr(probe, "fetch", fake_fetch)

    with pytest.raises(RuntimeError, match="500"):
        probe.read_endpoint("x", "a/{year}/{level}/", 2022)


def test_an_endpoint_with_no_rows_does_not_vote_on_the_finding(monkeypatch):
    """`enrollment-headcount` returned nothing at any level. That is an absence
    of data, not an observation that it carries no CIP field, and the finding
    must not count it as evidence either way.
    """
    stub(monkeypatch, {"fall-enrollment": page(10, ENROLMENT_ROW),
                       "completions-cip-6": page(9, COMPLETIONS_ROW),
                       "api-endpoints": {"count": 1, "results": [
                           {"endpoint_url": "/api/v1/x/completions-cip-6/"}]}})

    measured = probe.measure(2022)

    assert "enrollment-headcount" in measured["endpoints_without_rows"]
    assert "enrollment-headcount" not in measured["endpoints_observed"]
    assert measured["endpoints_observed"], (
        "the finding must rest on at least one endpoint that answered")


def test_a_catalogue_without_a_usable_count_is_refused(monkeypatch):
    """A catalogue that stops reporting `count` cannot be told apart from a
    truncated one, and the negative finding rests on seeing the whole list.
    """
    stub(monkeypatch, {"api-endpoints": {
        "results": [{"endpoint_url": "/api/v1/x/completions-cip-6/"}]}})

    with pytest.raises(probe.Refused, match="no usable `count`"):
        probe.cip_endpoints()


def test_the_page_states_the_request_count_the_probe_makes():
    """The one number on the page that was typed rather than measured — and it
    was wrong, reading twenty-nine against twenty actual requests.
    """
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    doc = (ROOT / "docs" / "sources" / "enrolment.md").read_text(encoding="utf-8")

    counted = (sum(len(s["paths_tried"]) for s in record["enrolment"])
               + len(record["completions"]["paths_tried"]) + 1)
    assert record["requests"] == counted, (
        f"the record says {record['requests']} requests; its own paths_tried "
        f"arrays hold {counted}")

    words = {18: "eighteen", 19: "nineteen", 20: "twenty", 21: "twenty-one"}
    stated = words.get(counted, str(counted))
    assert f"{stated} requests in all" in doc.lower(), (
        f"the page does not say `{stated} requests in all`; the probe makes "
        f"{counted}")
