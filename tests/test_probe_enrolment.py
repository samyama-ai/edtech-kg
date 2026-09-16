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
import re

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

    with pytest.raises(probe.Refused, match="`count` is None"):
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


def test_an_endpoint_with_no_rows_is_partitioned_out_of_the_evidence(monkeypatch):
    """`enrollment-headcount` returned nothing at any level. That is an absence
    of data, not an observation that it carries no CIP field.

    Named for what it actually pins: the partition, not the finding. Excluding
    an endpoint with no rows cannot change `enrolment_is_by_programme` in either
    direction — it has `cip_fields == []` and `any()` already ignores those — so
    the substance here is that the record names the two sets apart, which is
    what the page's footnote rests on.
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


def test_a_run_where_nothing_answered_refuses_rather_than_concluding(monkeypatch):
    """The failure stepping over 404s introduced: if the wrapper renames its
    IPEDS paths, every enrolment request 404s and `any([])` is False — so
    without a guard the probe publishes the negative finding having read
    nothing. The completions side has always refused this; so must this one.
    """
    def fake_fetch(path: str) -> dict:
        if "completions-cip-6" in path:
            return page(9, COMPLETIONS_ROW)
        if "api-endpoints" in path:
            return {"count": 1, "results": [
                {"endpoint_url": "/api/v1/x/completions-cip-6/"}]}
        raise RuntimeError(f"404 on https://example/{path}")

    monkeypatch.setattr(probe, "fetch", fake_fetch)

    with pytest.raises(probe.Refused, match="answered 404 at every level"):
        probe.measure(2022)


def test_the_two_kinds_of_nothing_are_recorded_apart(monkeypatch):
    """A 404 at every level is `not_published`; answering with zero rows is
    `empty`. Collapsing them passed every other test in this file, so it is
    pinned here directly.
    """
    def only_404(path: str) -> dict:
        raise RuntimeError(f"404 on https://example/{path}")

    monkeypatch.setattr(probe, "fetch", only_404)
    gone = probe.read_endpoint("x", "a/{year}/{level}/", 2022)
    assert gone["no_rows_because"] == "not_published"

    stub(monkeypatch, {})  # every level answers, with nothing in it
    quiet = probe.read_endpoint("x", "a/{year}/{level}/", 2022)
    assert quiet["no_rows_because"] == "empty"


def test_the_refusal_says_which_kind_of_nothing_it_found(monkeypatch):
    """A renamed path and a year with no data are different failures. The first
    means the probe asks the wrong questions; the second that the source has
    nothing for this year. One message for both describes only the second.
    """
    stub(monkeypatch, {"completions-cip-6": page(9, COMPLETIONS_ROW),
                       "api-endpoints": {"count": 1, "results": [
                           {"endpoint_url": "/api/v1/x/completions-cip-6/"}]}})

    with pytest.raises(probe.Refused, match="every one was empty"):
        probe.measure(2022)


def test_a_non_integer_count_is_refused_like_the_catalogue_does(monkeypatch):
    """`cip_endpoints` demands an int; `read_endpoint` only checked for None, so
    a string count flowed through and failed later on a format spec.
    """
    stub(monkeypatch, {"fall-enrollment": {"count": "12", "results": []}})

    with pytest.raises(probe.Refused, match="not an integer"):
        probe.read_endpoint(
            "fall", "college-university/ipeds/fall-enrollment/{year}/{level}/",
            2022)


def test_the_request_count_matches_the_code_not_only_the_record():
    """`requests` is recomputed from the record elsewhere, which keeps the page
    and the record agreeing — but both stay consistent and both stay wrong if an
    endpoint is added to ENROLMENT and --record is not re-run. This ties the
    loop to the code's own constants.
    """
    record = json.loads(RECORD.read_text(encoding="utf-8"))

    from_code = sum(len(probe.LEVELS) if "{level}" in template else 1
                    for _, template in probe.ENROLMENT) + 2
    assert record["requests"] == from_code, (
        f"the record says {record['requests']} requests; ENROLMENT and LEVELS "
        f"describe {from_code}. Re-run `python -m etl.probe_enrolment --record`")


def test_every_per_level_figure_on_the_page_is_in_the_record():
    """The table quotes eleven counts. On a page that says nothing is typed, and
    in a round that exists because one typed number was wrong.
    """
    doc = (ROOT / "docs" / "sources" / "enrolment.md").read_text(encoding="utf-8")
    record = json.loads(RECORD.read_text(encoding="utf-8"))

    measured = {format(a["rows"], ",") for s in record["enrolment"] + [record["completions"]]
                for a in s["levels"] if a["rows"]}
    table = doc[doc.index("| endpoint |"):doc.index("Every figure in that table")]
    quoted = set(re.findall(r"\b\d{1,3}(?:,\d{3})+\b", table))
    assert quoted, "the table quotes no figures — has it been reshaped?"
    assert quoted <= measured, (
        f"the table states {sorted(quoted - measured)}, which the record does "
        f"not hold")
