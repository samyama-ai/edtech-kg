"""The licence readers, and the page they produced.

No test here fetches anything. Every reader in `etl.licence_positions` takes
page TEXT rather than a URL, so these hand it fixtures directly instead of
monkeypatching a fetch — the seam exists precisely so the indirection does not
have to be rebuilt here.

The PAGE and the record are checked in `tests/test_licences_doc.py`, which is
where they moved when this file passed the 500-line limit. This one is the
readers and the fetch boundary only — the docstring went on describing the
other half after the split, along with a `record` fixture nothing here uses.
"""

from __future__ import annotations

import re

import pytest

from etl import licence_positions as lp


DATABASE_PAGE = """
<html><head><style>p { color: red }</style></head><body>
<script>var licence = "this is not the licence";</script>
<h1>O*NET&reg; 31.0 Database Content License</h1>
<p>Except as noted below, the content of the O*NET 31.0 Database is licensed
under a <a href="#">Creative Commons Attribution 4.0 International License</a>.</p>
<p>This page includes information from the O*NET 31.0 Database by the U.S.
Department of Labor, Employment and Training Administration (USDOL/ETA). Used
under the CC BY 4.0 license. O*NET&reg; is a trademark of USDOL/ETA.</p>
<p>If you make edits or additions to O*NET information: This page includes
information from the O*NET 31.0 Database by the U.S. Department of Labor,
Employment and Training Administration (USDOL/ETA). Used under the CC BY 4.0
license. O*NET&reg; is a trademark of USDOL/ETA. [Your name or company] has
modified all or some of this information. USDOL/ETA has not approved,
endorsed, or tested these modifications.</p>
<h2>License Exceptions</h2>
<p>This license applies only to downloadable files on the following pages:</p>
<ul><li>O*NET Database</li><li>Database Releases Archive</li>
<li>Spanish Language Resources</li></ul>
<p>To copy or adapt information from the O*NET Career Exploration Tools, see
the Career Exploration Tools License page.</p>
<p>&lt;keep-this-text&gt;</p>
</body></html>
"""

CROSSWALKS_PAGE = """
<html><body>
<h1>Education (CIP), DOT, Apprenticeship (RAPIDS)</h1>
<a href="a.xlsx">Classfication of Instructional Programs (CIP) (XLSX)</a>
<a href="b.xlsx">Registered Apprenticeship Partners Information Data System
(RAPIDS) (XLSX)</a>
<footer>Crosswalk Files by U.S. Department of Labor, Employment and Training
Administration is licensed under a Creative Commons Attribution 4.0
International License.</footer>
</body></html>
"""

URBAN_PAGE = """
<html><body><h2>Data Policy and Terms of Use</h2>
<p>All data made available via the Education Data Portal in any form is
licensed to you under the <a href="#">Open Data Commons Attribution License
(ODC-By) v1.0</a>.</p>
<h3>Citing these data</h3>
<p>[dataset names], Education Data Portal (Version ), Urban Institute,
accessed Month, DD, YYYY, https://educationdata.urban.org/documentation/,
made available under the ODC Attribution License.</p>
</body></html>
"""


def test_script_and_style_are_removed_before_the_tags_are():
    """The bug that made the first version refuse a page it had loaded.

    Strip tags first and the page's inline JavaScript survives as prose. On
    the real O*NET page that is most of what is left, and the word "licence"
    appears inside it — so the failure is not an empty result, it is a
    plausible wrong one.
    """
    flat = lp.flatten(DATABASE_PAGE)
    assert "this is not the licence" not in flat
    assert "color: red" not in flat


def test_entities_are_decoded_after_the_tags_and_not_before():
    """`O*NET&reg;` has to become `O*NET®` or the version is unreachable.

    Both halves are needed and the second is the one that pins the ORDER.
    Decoding first also produces `O*NET®`, so the first two assertions pass
    either way — they were the whole test, and swapping the order survived
    them. `&lt;keep-this-text&gt;` decodes to something the tag-stripper eats,
    so it is present only when the entities are decoded last.
    """
    flat = lp.flatten(DATABASE_PAGE)
    assert "O*NET® 31.0" in flat
    assert "&reg;" not in flat
    assert "keep-this-text" in flat


def test_the_database_licence_is_read_with_its_exception_list():
    read = lp.onet_database(DATABASE_PAGE)
    assert read["version"] == "31.0"
    assert read["licence"].startswith("Except as noted below")
    assert read["attribution"].endswith("trademark of USDOL/ETA.")
    assert "Spanish Language Resources" in read["applies_only_to"]


def test_the_exception_list_does_not_name_the_crosswalks_page():
    """The finding the whole document rests on.

    Asserted on the extracted list rather than on prose in the doc, so it
    fails if O*NET ever adds the crosswalks page and the page's argument
    stops being true.
    """
    applies_to = lp.onet_database(DATABASE_PAGE)["applies_only_to"]
    assert "rosswalk" not in applies_to


def test_the_crosswalk_files_carry_their_own_notice():
    read = lp.onet_crosswalks(CROSSWALKS_PAGE)
    assert read["licence"].startswith("Crosswalk Files by U.S. Department of Labor")
    assert len(read["files_this_repo_reads"]) == 2


def test_a_crosswalks_page_naming_neither_workbook_is_refused():
    """An empty list read as an ordinary result while saying the opposite.

    The notice on that page is what clears the two workbooks this repo reads.
    A page carrying the notice and naming neither file does not clear them —
    but `files_this_repo_reads: []` alongside a perfectly good licence string
    looks like a page that simply lists nothing, and the caller records it as
    cleared.
    """
    moved = CROSSWALKS_PAGE.replace("Classfication", "Renamed").replace(
        "Registered Apprenticeship Partners", "Renamed Apprenticeship")
    assert moved != CROSSWALKS_PAGE
    with pytest.raises(lp.MalformedSource, match="named neither workbook"):
        lp.onet_crosswalks(moved)


def test_one_workbook_renamed_is_recorded_not_refused():
    """A publisher retiring one file is ordinary; retiring both is not.

    Refusing on either would make an unremarkable rename look like a licence
    failure, which is the direction that gets a guard switched off.
    """
    one_gone = CROSSWALKS_PAGE.replace("Classfication", "Renamed")
    assert one_gone != CROSSWALKS_PAGE
    read = lp.onet_crosswalks(one_gone)
    assert read["files_this_repo_reads"] == [
        "Registered Apprenticeship Partners Information Data System (RAPIDS)"]
    assert read["licence"].startswith("Crosswalk Files")


def test_the_urban_portal_licence_and_citation_are_read():
    read = lp.urban_portal(URBAN_PAGE)
    assert "(ODC-By) v1.0" in read["licence"]
    assert read["citation"].startswith("[dataset names]")


@pytest.mark.parametrize("reader,page,missing,names", [
    (lp.onet_database, DATABASE_PAGE, "Creative Commons Attribution 4.0",
     "the Creative Commons licence sentence"),
    (lp.onet_crosswalks, CROSSWALKS_PAGE, "Crosswalk Files by",
     "the crosswalk files licence notice"),
    (lp.urban_portal, URBAN_PAGE, "Open Data Commons",
     "the Open Data Commons licence sentence"),
])
def test_a_page_without_its_licence_sentence_is_refused(reader, page, missing, names):
    """A cookie wall answers 200. Every field then comes back blank.

    `match=` names the SPECIFIC guard. Matching on "Refusing rather than" —
    the boilerplate every `_one` call shares — is exactly the failure this
    test's own docstring warned about: it passes when a different guard fires,
    so a reader whose own guard had been deleted stayed green as long as
    something else refused first.

    The removal is asserted too. A `replace` that matches nothing presents an
    intact page to a refusal test.
    """
    damaged = page.replace(missing, "REMOVED")
    assert damaged != page, f"{missing!r} is not in the fixture as written"
    with pytest.raises(lp.MalformedSource, match=re.escape(names)):
        reader(damaged)


# --------------------------------------------------------------------------
# the fetch boundary — a failure to reach is not a failure to publish
# --------------------------------------------------------------------------

def test_a_page_that_does_not_answer_raises_unreachable(monkeypatch):
    """Two different facts, and only one is about the publisher.

    Reporting a timeout as `MalformedSource` invites the next reader to
    conclude the terms changed. `Unreachable` subclasses it, so every existing
    handler still catches it and the CLI keeps one exit code.
    """
    def refuse(*_a, **_k):
        raise OSError("connection reset")

    monkeypatch.setattr(lp.urllib.request, "urlopen", refuse)
    with pytest.raises(lp.Unreachable, match="did not answer"):
        lp.page_text("https://example.invalid/terms")
    # And it is still a MalformedSource, or `main` stops catching it.
    assert issubclass(lp.Unreachable, lp.MalformedSource)


def test_the_response_charset_is_honoured_not_assumed(monkeypatch):
    """These are three third-party pages quoted VERBATIM as licence positions.

    A publisher serving Latin-1 would have turned every accented character in
    a quoted sentence into a replacement character, silently.
    """
    # No em dash: it has no Latin-1 encoding, and the fixture must be a page
    # a publisher could actually serve.
    body = "Café Frais licence".encode("latin-1")

    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "latin-1")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return body

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    read = lp.page_text("https://example.test/x")
    assert "Café Frais" in read
    # Decoded as UTF-8 the accented byte is a replacement character, so this
    # fails loudly if the charset is ignored rather than passing on a
    # substring that happens to survive.
    assert "\ufffd" not in read


def test_an_unknown_charset_falls_back_rather_than_raising(monkeypatch):
    """A codec name Python does not know must not become a traceback."""
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "not-a-real-codec")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return b"plain text"

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert lp.page_text("https://example.test/x") == "plain text"


def test_each_reader_refuses_in_words_that_name_its_own_guard():
    """Why `match=` on the shared boilerplate is not a test.

    Every `_one` refusal ends "Refusing rather than recording a blank", so
    matching that passes whenever ANY guard fires — including one belonging to
    a different reader. The three `what` strings have to be distinct, or the
    parametrised refusal tests above cannot tell which guard they exercised.
    """
    said = {}
    for reader, page, missing in (
            (lp.onet_database, DATABASE_PAGE, "Creative Commons Attribution 4.0"),
            (lp.onet_crosswalks, CROSSWALKS_PAGE, "Crosswalk Files by"),
            (lp.urban_portal, URBAN_PAGE, "Open Data Commons")):
        with pytest.raises(lp.MalformedSource) as raised:
            reader(page.replace(missing, "REMOVED"))
        said[reader.__name__] = str(raised.value)

    assert len(said) == 3
    # Distinct beyond the shared sentence: strip it and they must still differ.
    stripped = {name: message.replace("Refusing rather than recording a blank.", "")
                for name, message in said.items()}
    assert len(set(stripped.values())) == 3, \
        f"two readers refuse in the same words: {stripped}"


def test_the_request_identifies_this_project_and_bounds_the_wait(monkeypatch):
    """The header three publishers see when this repo reaches them.

    `USER_AGENT` is how O*NET, the Urban Institute and Credential Engine
    identify this traffic — the same courtesy the state-department probe found
    was not enough on its own, and the reason the 403s there could be
    characterised at all. Neither it nor the timeout had an assertion.
    """
    seen = {}

    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return b"body"

    def capture(request, timeout=None):
        seen["agent"] = request.get_header("User-agent")
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(lp.urllib.request, "urlopen", capture)
    lp.page_text("https://example.test/terms")

    assert seen["agent"] == lp.USER_AGENT
    assert "edtech-kg" in seen["agent"] and "git.samyama.ai" in seen["agent"], (
        "the agent must name the project and where to complain about it")
    assert seen["timeout"], "an unbounded fetch can hang the probe forever"


@pytest.mark.parametrize("charset", ["idna", "undefined"])
def test_a_charset_python_refuses_falls_back_rather_than_raising(charset, monkeypatch):
    """`LookupError` alone did not cover these.

    `idna` and `undefined` are codecs Python knows and refuses for bytes,
    raising `UnicodeError` — so they escaped a guard written for an unknown
    name and reached the caller as a traceback.

    `punycode` is deliberately not here: it does not raise, it decodes to
    nonsense. That is a different problem and this guard is not the fix for
    it; a fixture using it would have tested nothing.
    """
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: charset)})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return b"plain text"

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert lp.page_text("https://example.test/x") == "plain text"


def test_an_enormous_body_is_refused_rather_than_read(monkeypatch):
    """`timeout` bounds a socket operation, not a transfer.

    A slow drip had no ceiling, and `flatten`'s script-strip is quadratic — so
    a body of unterminated `<script` tokens costs far more than its size. On
    three licence pages, anything past a few megabytes is not one of them.
    """
    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None):
            return b"x" * (amount if amount else lp.MAX_PAGE + 1)

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(lp.MalformedSource, match="more than"):
        lp.page_text("https://example.test/x")


def test_a_body_within_the_cap_is_read_whole(monkeypatch):
    """The false-positive direction — the cap must not truncate a real page."""
    body = b"a" * (lp.MAX_PAGE // 2)

    class Response:
        headers = type("H", (), {
            "get_content_charset": staticmethod(lambda: "utf-8")})()
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, amount=None): return body

    monkeypatch.setattr(lp.urllib.request, "urlopen", lambda *a, **k: Response())
    assert len(lp.page_text("https://example.test/x")) == len(body)
