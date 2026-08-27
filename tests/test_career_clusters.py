"""Reading a licence off two web pages, and refusing to read one that did not load.

Split out of `tests/test_probe_codesets.py` when it passed the 500-line review
limit, on the boundary `docs/sources/code-sets.md` already draws: everything
else in that file MEASURES a code set, and this section is a **reading of a
licence**, which the page says outright.

That distinction is why these guards matter more than their size suggests. A
measurement that comes back wrong is a wrong number; a licence position that
comes back wrong from a page nobody could read is a statement about what this
project may legally use. Both pages that feed it are guarded here, and the
blocker that reached review was guarding only one of them.
"""

from __future__ import annotations

import pytest

from etl import probe_codesets as probe


#: A crosswalks page that looks like the real one: links to published files.
CROSSWALKS_PAGE = (b'<html><body>'
                   b'<a href="/files/CareerClustersWheel-key.pdf">wheel</a>'
                   b'</body></html>')


def serve(monkeypatch, page: bytes, *, crosswalks: bytes = CROSSWALKS_PAGE):
    """Answer every fetch, per URL, with ONE stub.

    There were six copies of a three-line `Response` class, each answering
    every URL with the same body — so a test aiming a fixture at the framework
    page was also answering the crosswalks page with it, and no test could
    tell the two apart. `career_clusters` reads both.
    """
    bodies = {probe.CLUSTERS: page, probe.CLUSTER_CROSSWALKS: crosswalks}

    class Response:
        def __init__(self, body): self._body = body
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self): return self._body

    def urlopen(request, *a, **k):
        url = request if isinstance(request, str) else request.full_url
        return Response(bodies.get(url, page))

    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)


def test_no_machine_readable_file_is_reported_only_when_there_is_none(monkeypatch):
    """The zero that feeds the licence conclusion.

    "0 machine-readable files" is the reason Career Clusters is recorded as not
    cleared, so a pattern that misses a real link would produce that conclusion
    from a false negative. The first pattern required double quotes and the
    extension at the very end of the href, so `'/x.xlsx?v=2'` counted as none.
    """
    bare = b"<html><p>14 Clusters and 72 Sub-Clusters</p><a href='/brand.pdf'>x</a></html>"
    serve(monkeypatch, bare)
    assert probe.career_clusters()["machine_readable_files"] == [], (
        "a PDF was counted as a machine-readable file")

    linked = bare.replace(b"<a href='/brand.pdf'>x</a>",
                          b"<a href='/clusters.xlsx?v=2'>x</a>"
                          b'<a href="/c.csv#tab">y</a>')
    serve(monkeypatch, linked)
    found = probe.career_clusters()["machine_readable_files"]
    assert found == ["/c.csv", "/clusters.xlsx"], (
        f"a published data file was missed, so the licence conclusion would "
        f"rest on a false zero — found {found}")


def test_the_copyright_notice_survives_a_full_stop(monkeypatch):
    """The first version of this pattern stopped at the first full stop and
    found nothing — reporting no notice on a page that carries one, which is
    the wrong way round for a licence check."""
    page = ('<html><footer>© 2023 Advance CTE: State Leaders Connecting '
            'Learning to Work. All rights reserved.</footer>'
            '<p>14 Clusters and 72 Sub-Clusters</p></html>').encode()

    serve(monkeypatch, page)

    got = probe.career_clusters()
    assert got["copyright_notice"], "the notice was not found on a page that has one"
    assert "All rights reserved" in got["copyright_notice"]
    assert (got["clusters"], got["sub_clusters"]) == (14, 72)
    assert got["measured_or_read"] == "read", (
        "a licence position is a reading, and the result must say so")


def test_the_licence_zero_is_counted_on_the_page_the_prose_describes(monkeypatch):
    """The conclusion rested on a page the probe never fetched.

    `machine_readable_files` counted links on the framework LANDING page, while
    the document's corroborating sentence describes the CROSSWALKS page — "the
    files actually published on the crosswalks page are PDFs". A zero measured
    somewhere other than where the sentence points is not corroborated by it.

    Both pages are fetched now, counted separately, and the PDFs are named
    rather than described.
    """
    pages = {
        probe.CLUSTERS: ("<html><p>14 Clusters and 72 Sub-Clusters</p>"
                         "<footer>© 2023 Advance CTE. All rights reserved.</footer>"
                         "<a href='/framework.xlsx'>x</a></html>"),
        probe.CLUSTER_CROSSWALKS: ("<html><a href='/grid.pdf'>a</a>"
                                   "<a href='/wheel.pdf'>b</a></html>"),
    }
    monkeypatch.setattr(probe, "page_text", lambda url: pages[url])

    got = probe.career_clusters()
    assert got["machine_readable_files"] == ["/framework.xlsx"], (
        "the framework page's own data files are no longer counted")
    assert got["machine_readable_on_crosswalks"] == [], (
        "the crosswalks page was not counted separately, so the licence zero "
        "is again measured somewhere other than where the prose points")
    assert got["pdfs_on_crosswalks"] == ["grid.pdf", "wheel.pdf"], (
        "the PDFs are described rather than named")


def test_a_data_link_with_a_mismatched_quote_is_not_counted():
    """`href="a.csv'` matched, because the pattern did not backreference the
    opening quote. Harmless for the count today and wrong as a rule."""
    assert probe.data_files('''<a href="a.csv">''') == ["a.csv"]
    assert probe.data_files("""<a href='b.xlsx?v=2'>""") == ["b.xlsx"]
    assert probe.data_files('''<a href="c.csv\'>''') == [], (
        "a mismatched quote pair was counted as a published data file")


def test_a_pdf_link_with_a_mismatched_quote_is_not_counted(monkeypatch):
    """The same bug as `data_files`, three lines away.

    The fix backreferenced one regex and not the other, and the test written
    to prevent it only covered the one that already had it. The PDF count
    feeds the licence conclusion too.
    """
    pages = {
        probe.CLUSTERS: "<html><p>14 Clusters and 72 Sub-Clusters</p></html>",
        probe.CLUSTER_CROSSWALKS: ("<html><a href='/good.pdf'>a</a>"
                                   "<a href=\"/bad.pdf'>b</a></html>"),
    }
    monkeypatch.setattr(probe, "page_text", lambda url: pages[url])
    got = probe.career_clusters()
    assert got["pdfs_on_crosswalks"] == ["good.pdf"], (
        f"a mismatched quote pair was counted as a published PDF: "
        f"{got['pdfs_on_crosswalks']}")


def test_a_page_that_did_not_load_is_refused_rather_than_counted_as_a_zero(monkeypatch):
    """The zero the licence position is argued from must have one meaning.

    `career_clusters()` validated nothing about what came back, unlike
    `download()`, which checks the PK magic before believing it has a workbook.
    A redirect, a cookie wall or a JavaScript shell answers 200 with no
    content: every field comes back `None` or `[]`, and the probe printed
    "None clusters, None sub-clusters" and "data files ... 0" without
    complaining.

    `docs/sources/code-sets.md` rests "NOT cleared" on that zero. A genuine
    absence of machine-readable files and a failed fetch produced the same
    number, and nothing let a reader — or a re-run months later — tell them
    apart. A licence conclusion is the last thing that should rest on a figure
    with two meanings.
    """
    shell = b"<html><body><div id=root></div><script src=/app.js></script></body></html>"

    serve(monkeypatch, shell)

    with pytest.raises(probe.MalformedSource) as refused:
        probe.career_clusters()
    assert "not that page" in str(refused.value)


def test_an_ordinary_edit_to_the_page_does_not_break_the_probe(monkeypatch):
    """BOTH landmarks must be missing to refuse, not either one.

    Advance CTE can reword a copyright line or restate the cluster count
    without the page having failed to load. Refusing on one missing landmark
    would turn an ordinary edit into a broken probe and lose the reading
    entirely — which is the same failure as reporting a false zero, in the
    other direction.
    """
    reworded = (b"<html><body><p>14 Clusters and 72 Sub-Clusters</p>"
                b"<p>Copyright Advance CTE, all rights are reserved.</p></body></html>")

    serve(monkeypatch, reworded)

    got = probe.career_clusters()
    assert (got["clusters"], got["sub_clusters"]) == (14, 72)
    assert got["copyright_notice"] is None, (
        "the fixture reworded the notice; the point is that the probe still "
        "reads the page rather than refusing it")


def test_a_crosswalks_page_that_did_not_load_is_refused_too(monkeypatch):
    """The half of the blocker that was left open.

    The first fix guarded `CLUSTERS` and nothing checked `CLUSTER_CROSSWALKS`
    — and the crosswalks page is where BOTH corroborating figures come from.
    A failed load there returned `machine_readable_on_crosswalks: []` and
    `pdfs_on_crosswalks: []`, so the zero the licence position rests on was
    still reachable from a page that never loaded, and the "6 PDFs" that
    corroborate it vanished with nothing saying so.

    Guarding one of two pages that feed a conclusion is not guarding the
    conclusion, and the mutation that removed this guard passed the whole
    suite — which is how it shipped the first time.
    """
    good = (b"<html><footer>\xc2\xa9 2023 Advance CTE: State Leaders Connecting "
            b"Learning to Work. All rights reserved.</footer>"
            b"<p>14 Clusters and 72 Sub-Clusters</p></html>")

    serve(monkeypatch, good, crosswalks=b"<html><div id=root></div></html>")
    with pytest.raises(probe.MalformedSource, match="no links to published files"):
        probe.career_clusters()

    # And a crosswalks page that DID load still reads, so the guard refuses
    # the failure rather than refusing the page.
    serve(monkeypatch, good)
    assert probe.career_clusters()["pdfs_on_crosswalks"] == [
        "CareerClustersWheel-key.pdf"]


def test_a_pdf_link_with_a_query_string_is_still_counted(monkeypatch):
    """The corroboration must not under-report for the same reason the zero
    must not over-report.

    `data_files` allows a query string after the extension, because
    `/x.xlsx?v=2` is a real link. This regex carried a comment claiming parity
    with it and did not have that allowance, so `/wheel.pdf?ver=3` counted as
    no PDF — and the PDF count is what corroborates the zero beside it.
    """
    good = (b"<html><footer>\xc2\xa9 2023 Advance CTE. All rights reserved.</footer>"
            b"<p>14 Clusters and 72 Sub-Clusters</p></html>")
    crosswalks = (b'<html><a href="/files/wheel.pdf?ver=3">a</a>'
                  b"<a href='/files/grid.pdf#page2'>b</a>"
                  b'<a href="/files/plain.pdf">c</a></html>')

    serve(monkeypatch, good, crosswalks=crosswalks)
    found = probe.career_clusters()["pdfs_on_crosswalks"]
    assert found == ["grid.pdf", "plain.pdf", "wheel.pdf"], (
        f"a published PDF was missed because of its query string or fragment, "
        f"so the count that corroborates the zero under-reports — found {found}")
