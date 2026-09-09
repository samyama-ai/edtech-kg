"""The graduation probe's robots gate, driven without the network.

The gate is the whole point: a probe that fetches first and asks afterwards
has not asked. Everything here checks that the refusal path is reachable, is
returned as data, and cannot be walked past.
"""

from __future__ import annotations

import pytest

from etl import probe_graduation as probe


def test_a_blanket_disallow_stops_the_fetch(monkeypatch):
    """**The finding this issue turns on.** `reports.ecs.org` is
    `Disallow: /`, and a probe that read the compilation anyway would have
    taken something it was told not to."""
    asked = []

    def only_robots(url, *a, **k):
        asked.append(url)
        return (200, "User-agent: *\nDisallow: /\n")

    monkeypatch.setattr(probe, "DELAY", 0)
    monkeypatch.setattr(probe, "_read", only_robots, raising=False)
    monkeypatch.setattr(probe.urllib.request, "urlopen", _reader(
        {"https://x.test/robots.txt": "User-agent: *\nDisallow: /\n"}))
    found = probe.fetch("https://x.test/data")
    assert found["allowed"] is False
    assert found["fetched"] is False
    assert found["status"] is None, "a disallowed page was requested anyway"


def _reader(pages):
    """A urlopen that serves a dict and refuses everything else."""
    class Response:
        def __init__(self, body):
            self._body = body.encode()
            self.status = 200

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(request, timeout=None):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if url in pages:
            return Response(pages[url])
        raise AssertionError(f"the probe requested {url}, which robots forbade")

    return urlopen


def test_an_allowed_path_is_fetched(monkeypatch):
    """The negative must be reachable only by asking. A gate that refused
    everything would make "nothing was fetched" true of any input."""
    monkeypatch.setattr(probe, "DELAY", 0)
    monkeypatch.setattr(probe.urllib.request, "urlopen", _reader({
        "https://y.test/robots.txt": "User-agent: *\nDisallow: /private/\n",
        "https://y.test/data": "<table><tr><td>x</td></tr></table>",
    }))
    found = probe.fetch("https://y.test/data")
    assert found["allowed"] is True
    assert found["fetched"] is True
    assert found["status"] == 200


def test_a_missing_robots_file_permits(monkeypatch):
    """The convention. Refusing on a 404 would report every host without
    published rules as forbidding us."""
    import urllib.error

    def urlopen(request, timeout=None):
        url = request.full_url
        if url.endswith("robots.txt"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _reader({url: "<html>ok</html>"})(request, timeout)

    monkeypatch.setattr(probe, "DELAY", 0)
    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)
    found = probe.fetch("https://z.test/data")
    assert found["allowed"] is True
    assert "absence permits" in found["why"]


def test_a_footnote_row_is_not_a_state():
    """NCES puts its footnotes and its SOURCE line in the same table as
    single-cell rows. Counting those gave 85 "states" — more than there are,
    which is the kind of wrong that should be obvious and was only obvious
    because someone read it."""
    body = ("<table>"
            "<tr><th>State</th><th>A</th><th>B</th></tr>"
            "<tr><td>Alabama</td><td>4</td><td>3</td></tr>"
            "<tr><td>Alaska</td><td>4</td><td>3</td></tr>"
            "<tr><td>1 A footnote spanning the table.</td></tr>"
            "<tr><td>SOURCE: Somebody, retrieved yesterday.</td></tr>"
            "</table>")
    found = probe.shape_of({"body": body})
    assert found["rows"] == 2
    assert found["distinct_states"] == 2
    assert found["rows_that_are_not_data"] == 2


def test_a_blank_first_column_is_not_a_state():
    """A spacer row carried an empty name and counted as a jurisdiction."""
    body = ("<table>"
            "<tr><th>State</th><th>A</th><th>B</th></tr>"
            "<tr><td>Alabama</td><td>4</td><td>3</td></tr>"
            "<tr><td></td><td></td><td></td></tr>"
            "</table>")
    assert probe.shape_of({"body": body})["distinct_states"] == 1


def test_the_requirement_shapes_are_told_apart():
    """The issue's second question — how many states express requirements as
    credits-per-subject versus named courses versus prose. Only the first
    structures cleanly, and the counts are the answer."""
    body = ("<table>"
            "<tr><th>State</th><th>Type</th><th>English</th></tr>"
            "<tr><td>A</td><td>Standard</td><td>4</td></tr>"
            "<tr><td>B</td><td>Standard</td><td>4, incl. English I, II</td></tr>"
            "<tr><td>C</td><td>Standard</td><td>4 units or ESL*</td></tr>"
            "</table>")
    found = probe.shape_of({"body": body})
    assert found["cells_as_a_bare_credit_count"] == 1
    assert found["cells_naming_courses_as_well"] == 1
    assert found["cells_in_prose"] == 1
    assert found["percent_cleanly_structurable"] == 33.3


def test_a_page_with_no_table_says_so_rather_than_reporting_zero():
    """A page publishing no table has not published requirements of no
    shape — it has not answered the question."""
    found = probe.shape_of({"body": "<html>nothing here</html>"})
    assert found["tables"] == 0
    assert "not published as one" in found["note"]


def test_the_source_line_is_captured():
    """"The federal route is not independent" is a claim about provenance."""
    said = probe.cites("<p>SOURCE: Education Commission of the States, "
                       "Age Requirements, retrieved January 8, 2018.</p>")
    assert said and "Education Commission of the States" in said[0]
