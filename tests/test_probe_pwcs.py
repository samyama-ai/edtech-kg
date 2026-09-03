"""Tests for the PWCS catalogue probe.

The network and the cache are stubbed throughout. Under test: reading the
prerequisite out of its own markup block rather than out of flattened page text,
resolving links by URL, and the refusals.

The bug this file pins hardest: an earlier version flattened the page to text
and matched `Prerequisite:\\s*(...)`, which ran the value into the page footer
and turned the school's street address into a course name. It also read
"Prerequisite: None" — an explicit statement that a course has none — as a
stated prerequisite.
"""

import json

import pytest

from etl import probe_pwcs as probe


COURSE = """<html>
<nav><a href="/">Home</a><a href="/agriculture">Agriculture</a>
     <a href="/agriculture/landscaping-1">Landscaping 1</a></nav>
<h1>Landscaping 2</h1>
<div class="field field--name-field-recommended field--type-text-long">
  <div class="field__label">Requirements</div>
  <div class="field__item"><p>Enrolled in Agriculture Specialty Program</p></div>
</div>
<div><h3>Prerequisites</h3>
  <div class="field field--name-field-prerequisite-courses field__items">
    <div class="field__item">
      <a href="/agriculture/landscaping-1">Landscaping 1</a>
    </div>
  </div>
</div>
<footer><a href="/contact">Contact</a>14715 Bristow Rd</footer></html>"""

NO_PREREQ = """<html>
<nav><a href="/">Home</a><a href="/agriculture/landscaping-2">Landscaping 2</a></nav>
<h1>Landscaping 1</h1>
<div class="field field--name-field-description"><p>An introduction.</p></div>
<footer>14715 Bristow Rd</footer></html>"""


def serve(monkeypatch, pages: dict):
    """Serve markup by URL, and disable the on-disk cache."""
    def fetch(url, use_cache=True):
        if url not in pages:
            raise RuntimeError(f"404 from {url}")
        return pages[url]
    monkeypatch.setattr(probe, "fetch", fetch)


# --------------------------------------------------------------------------
# parsing — the value must come from its own block, not from page text
# --------------------------------------------------------------------------

def test_the_prerequisite_is_read_as_links_not_as_prose():
    r = probe.parse_course(COURSE, "https://x/agriculture/landscaping-2")
    assert [l["name"] for l in r["prerequisite_links"]] == ["Landscaping 1"]
    assert [l["href"] for l in r["prerequisite_links"]] == ["/agriculture/landscaping-1"]


def test_the_page_footer_does_not_leak_into_the_prerequisite():
    """Flattening the page ran the value into the footer and produced
    "Landscaping 1 14715 Bristow Rd" as a course name."""
    r = probe.parse_course(COURSE, "https://x/a/b")
    assert all("Bristow" not in l["name"] for l in r["prerequisite_links"])


def test_free_text_requirements_are_kept_apart_from_linked_prerequisites():
    """"Enrolled in Agriculture Specialty Program" is a condition, not a course
    reference. Counting it as one would overstate what can be loaded."""
    r = probe.parse_course(COURSE, "https://x/a/b")
    assert r["requirements_text"] == "Enrolled in Agriculture Specialty Program"
    assert len(r["prerequisite_links"]) == 1


def test_a_course_with_no_prerequisite_block_has_no_links():
    """The page still carries navigation links, including one to another
    course. Scanning the whole page for <a href> would invent a prerequisite."""
    r = probe.parse_course(NO_PREREQ, "https://x/a/landscaping-1")
    assert r["prerequisite_links"] == []
    assert r["title"] == "Landscaping 1"


def test_navigation_links_are_not_prerequisites():
    """The nav bar links to Landscaping 1 and the footer to /contact. Only the
    prerequisite block counts — one link, not four."""
    r = probe.parse_course(COURSE, "https://x/a/landscaping-2")
    assert len(r["prerequisite_links"]) == 1
    hrefs = [l["href"] for l in r["prerequisite_links"]]
    assert "/" not in [h for h in hrefs] and "/contact" not in hrefs


def test_a_page_that_ends_at_the_prerequisite_block_still_parses():
    """The block regex only matches when something follows it. A page whose
    markup ends right after the prerequisites reported zero — a silent zero,
    which reads as "this district publishes none"."""
    truncated = COURSE.split("<footer")[0]
    r = probe.parse_course(truncated, "https://x/a/landscaping-2")
    assert len(r["prerequisite_links"]) == 1


def test_a_page_without_a_heading_is_not_a_course():
    assert probe.parse_course("<html><p>nothing</p></html>", "https://x/y") is None


def test_a_404_page_is_not_counted_as_a_course():
    """Otherwise it becomes a course with no prerequisite, quietly lowering
    the rate."""
    assert probe.parse_course("<html><h1>Page not found</h1></html>", "https://x/y") is None


# --------------------------------------------------------------------------
# resolution — by URL, against the whole catalogue
# --------------------------------------------------------------------------

def records():
    return [probe.parse_course(COURSE, "https://catalog.pwcs.edu/agriculture/landscaping-2"),
            probe.parse_course(NO_PREREQ, "https://catalog.pwcs.edu/agriculture/landscaping-1")]


def test_a_link_to_a_published_course_resolves():
    r = probe.resolve(records(), catalogue=["https://catalog.pwcs.edu/agriculture/landscaping-1"])
    assert r["stating_a_prerequisite"] == 1
    assert r["every_link_resolves"] == 1
    assert r["resolvable_edges"] == 1
    assert r["dangling_links"] == 0


def test_a_link_to_nothing_is_counted_as_dangling():
    page = COURSE.replace("/agriculture/landscaping-1", "/agriculture/does-not-exist")
    recs = [probe.parse_course(page, "https://catalog.pwcs.edu/agriculture/landscaping-2")]
    r = probe.resolve(recs, catalogue=["https://catalog.pwcs.edu/agriculture/landscaping-1"])
    assert r["no_link_resolves"] == 1
    assert r["dangling_links"] == 1
    assert r["resolvable_edges"] == 0


def test_resolution_uses_the_whole_catalogue_not_only_the_pages_read():
    """A partial run resolved against the handful of pages it had fetched and
    reported almost everything as broken — an artefact of the sample that read
    like a finding. The sitemap gives the full course list for free."""
    recs = [probe.parse_course(COURSE, "https://catalog.pwcs.edu/agriculture/landscaping-2")]
    without = probe.resolve(recs, catalogue=[])
    with_full = probe.resolve(recs, catalogue=["https://catalog.pwcs.edu/agriculture/landscaping-1"])
    assert without["no_link_resolves"] == 1
    assert with_full["every_link_resolves"] == 1


def test_a_trailing_slash_does_not_break_resolution():
    """Only the linking course is passed, so resolution must come from the
    catalogue URL rather than from the target's own record — which is what let
    this pass while the path comparison was slash-sensitive."""
    recs = [probe.parse_course(COURSE, "https://catalog.pwcs.edu/agriculture/landscaping-2")]
    r = probe.resolve(recs, catalogue=["https://catalog.pwcs.edu/agriculture/landscaping-1/"])
    assert r["every_link_resolves"] == 1
    assert r["dangling_links"] == 0


def test_free_text_requirements_are_counted_separately():
    r = probe.resolve(records(), catalogue=[])
    assert r["with_free_text_requirements"] == 1


# --------------------------------------------------------------------------
# the sweep
# --------------------------------------------------------------------------

SITEMAP = ("<urlset><loc>https://catalog.pwcs.edu/agriculture/landscaping-1</loc>"
           "<loc>https://catalog.pwcs.edu/agriculture/landscaping-2</loc>"
           "<loc>https://catalog.pwcs.edu/high-school-course-catalog/welcome</loc></urlset>")


def test_catalogue_furniture_is_not_treated_as_a_course():
    """`/high-school-course-catalog/welcome` is a landing page. Counting it
    would add courses that have no prerequisite by definition."""
    def fetch(url, use_cache=True):
        return SITEMAP
    import etl.probe_pwcs as m
    original, m.fetch = m.fetch, fetch
    try:
        urls = probe.catalogue_urls()
    finally:
        m.fetch = original
    assert len(urls) == 2
    assert all("course-catalog" not in u for u in urls)


def test_a_sitemap_that_is_not_a_sitemap_is_refused(monkeypatch):
    serve(monkeypatch, {probe.SITEMAP: "<html>503 Service Unavailable</html>"})
    with pytest.raises(probe.MalformedSource, match="no <loc> entries"):
        probe.catalogue_urls()


def test_a_sitemap_with_no_course_pages_is_refused(monkeypatch):
    serve(monkeypatch, {probe.SITEMAP:
                        "<urlset><loc>https://catalog.pwcs.edu/high-school-course-catalog/x</loc></urlset>"})
    with pytest.raises(ValueError, match="refusing"):
        probe.catalogue_urls()


def test_a_page_that_cannot_be_read_is_reported_not_dropped(monkeypatch):
    """One slow page used to lose a 17-minute sweep. It is now retried and then
    recorded — a page we could not read is not a course without a prerequisite,
    and quietly excluding it would lower the rate with no trace."""
    serve(monkeypatch, {probe.SITEMAP: SITEMAP,
                        "https://catalog.pwcs.edu/agriculture/landscaping-1": NO_PREREQ})
    result = probe.probe(quiet=True)
    assert result["unread"] == 1
    assert result["courses"] == 1
    assert "landscaping-2" in result["unread_examples"][0]["url"]


def test_a_partial_run_says_it_is_partial(monkeypatch):
    serve(monkeypatch, {probe.SITEMAP: SITEMAP,
                        "https://catalog.pwcs.edu/agriculture/landscaping-1": NO_PREREQ,
                        "https://catalog.pwcs.edu/agriculture/landscaping-2": COURSE})
    partial = probe.probe(limit=1, quiet=True)
    full = probe.probe(quiet=True)
    assert "partial run, not the catalogue" in partial["coverage"]
    assert "every catalogue page" in full["coverage"]


def test_no_courses_parsed_is_refused(monkeypatch):
    serve(monkeypatch, {probe.SITEMAP: SITEMAP})
    with pytest.raises(ValueError, match="refusing"):
        probe.probe(quiet=True)


# --------------------------------------------------------------------------
# the CLI
# --------------------------------------------------------------------------

def test_a_limit_below_one_is_refused():
    assert probe.main(["--limit", "0"]) == 1


def test_a_malformed_sitemap_exits_three(monkeypatch):
    serve(monkeypatch, {probe.SITEMAP: "<html>down</html>"})
    assert probe.main([]) == 3


def test_an_unreachable_source_exits_two(monkeypatch):
    monkeypatch.setattr(probe, "catalogue_urls",
                        lambda use_cache=True: (_ for _ in ()).throw(RuntimeError("dns")))
    assert probe.main([]) == 2


def test_json_output_carries_a_timestamp_and_the_coverage(monkeypatch, capsys):
    serve(monkeypatch, {probe.SITEMAP: SITEMAP,
                        "https://catalog.pwcs.edu/agriculture/landscaping-1": NO_PREREQ,
                        "https://catalog.pwcs.edu/agriculture/landscaping-2": COURSE})
    assert probe.main(["--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "retrieved_at" in out and "coverage" in out


# --------------------------------------------------------------------------
# the third review of #63
# --------------------------------------------------------------------------

def test_a_rendered_field_with_no_links_is_flagged_not_read_as_absence():
    """The guard the comment promised and the code did not implement. If the
    markup drifts so HREF stops matching, every course silently becomes one
    without a prerequisite — the rate drops with no trace, which is the class
    of error this probe exists to correct."""
    drifted = COURSE.replace('<a href="/agriculture/landscaping-1">Landscaping 1</a>',
                             '<span data-href="/agriculture/landscaping-1">Landscaping 1</span>')
    r = probe.parse_course(drifted, "https://catalog.pwcs.edu/agriculture/landscaping-2")
    assert r["prerequisite_links"] == []
    assert r["field_present_no_links"] is True


def test_a_course_with_no_field_at_all_is_not_flagged():
    r = probe.parse_course(NO_PREREQ, "https://catalog.pwcs.edu/agriculture/landscaping-1")
    assert r["field_present_no_links"] is False


def test_the_unparsed_count_is_reported(monkeypatch):
    drifted = COURSE.replace('<a href="/agriculture/landscaping-1">Landscaping 1</a>',
                             '<span>Landscaping 1</span>')
    recs = [probe.parse_course(drifted, "https://catalog.pwcs.edu/agriculture/landscaping-2")]
    assert probe.resolve(recs, catalogue=[])["prerequisite_field_unparsed"] == 1


def test_an_empty_requirements_field_does_not_steal_later_text():
    """Unbounded, the pattern matched the *next* `field__item"><p>` anywhere
    later in the document and attributed unrelated text to this course —
    inflating the 138. Real pages carry several such fields after it, which is
    why the fixture must too."""
    page = COURSE.replace(
        '<div class="field__item"><p>Enrolled in Agriculture Specialty Program</p></div>',
        '<div class="field__item"></div>').replace(
        '<div><h3>Prerequisites</h3>',
        '<div class="field field--name-field-description">'
        '<div class="field__item"><p>An unrelated course description.</p></div></div>\n'
        '<div><h3>Prerequisites</h3>')
    r = probe.parse_course(page, "https://x/a/b")
    assert r["requirements_text"] is None, "stole the description field"


def test_the_requirements_field_is_still_read_when_it_has_a_value():
    """The bound must not break the happy path — 138 courses depend on it."""
    page = COURSE.replace(
        '<div><h3>Prerequisites</h3>',
        '<div class="field field--name-field-description">'
        '<div class="field__item"><p>An unrelated course description.</p></div></div>\n'
        '<div><h3>Prerequisites</h3>')
    r = probe.parse_course(page, "https://x/a/b")
    assert r["requirements_text"] == "Enrolled in Agriculture Specialty Program"


def test_resolution_is_strictly_against_the_sitemap():
    """`published` used to union the read records in, so resolution was partly
    self-referential and did not match what the docstring claimed."""
    recs = [probe.parse_course(COURSE, "https://catalog.pwcs.edu/agriculture/landscaping-2"),
            probe.parse_course(NO_PREREQ, "https://catalog.pwcs.edu/agriculture/landscaping-1")]
    r = probe.resolve(recs, catalogue=[])
    assert r["no_link_resolves"] == 1        # the target was read, but is not in the sitemap


def test_an_off_site_link_does_not_resolve():
    """An absolute URL on another host whose path coincidentally exists in the
    catalogue must not count toward a 100% claim."""
    page = COURSE.replace('href="/agriculture/landscaping-1"',
                          'href="https://example.com/agriculture/landscaping-1"')
    recs = [probe.parse_course(page, "https://catalog.pwcs.edu/agriculture/landscaping-2")]
    r = probe.resolve(recs, catalogue=["https://catalog.pwcs.edu/agriculture/landscaping-1"])
    assert r["no_link_resolves"] == 1
    assert r["dangling_links"] == 1


def test_an_absolute_link_on_the_catalogue_host_does_resolve():
    page = COURSE.replace('href="/agriculture/landscaping-1"',
                          'href="https://catalog.pwcs.edu/agriculture/landscaping-1"')
    recs = [probe.parse_course(page, "https://catalog.pwcs.edu/agriculture/landscaping-2")]
    r = probe.resolve(recs, catalogue=["https://catalog.pwcs.edu/agriculture/landscaping-1"])
    assert r["every_link_resolves"] == 1


def test_the_reported_path_count_is_the_set_used_for_resolution(monkeypatch):
    """`published_paths` reported a set built differently from the one
    resolution uses.

    No behavioural test can separate the two: inside `probe()` every record is
    parsed from a sitemap URL, so the old union was provably equal to the
    sitemap set. The fix is that the reported figure is now built the same way
    resolution builds its set, rather than happening to agree — so this asserts
    the count, and the invariant is stated rather than pretended to be
    observable."""
    serve(monkeypatch, {probe.SITEMAP: SITEMAP,
                        "https://catalog.pwcs.edu/agriculture/landscaping-1": NO_PREREQ,
                        "https://catalog.pwcs.edu/agriculture/landscaping-2": COURSE})
    result = probe.probe(quiet=True)
    assert result["published_paths"] == 2, "counted more than the sitemap publishes"
    assert result["published_paths"] == result["population"]


def test_the_cache_write_states_its_encoding():
    """A behavioural test cannot see this on a UTF-8 system, and the read
    states `encoding="utf-8"` — so the write must too, or the pair only agrees
    by accident of locale."""
    import inspect
    source = inspect.getsource(probe.fetch)
    write = [line for line in source.splitlines() if "write_text" in line]
    assert write, "no write in fetch()"
    assert all('encoding="utf-8"' in line for line in write), write


def test_a_cache_write_is_atomic(monkeypatch, tmp_path):
    """A direct write interrupted midway leaves a truncated page that every
    later run reads as though it were real — a silent wrong answer with no
    retry. Written to a sibling and renamed instead."""
    monkeypatch.setattr(probe, "CACHE", tmp_path)
    renamed = []
    real_replace = probe.Path.replace
    monkeypatch.setattr(probe.Path, "replace",
                        lambda self, target: (renamed.append(self.suffix), real_replace(self, target))[1])

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"<html><h1>X</h1></html>"
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())
    monkeypatch.setattr(probe.time, "sleep", lambda *a: None)

    probe.fetch("https://catalog.pwcs.edu/a/b")
    assert renamed == [".partial"], "wrote straight to the cache key"
    assert not list(tmp_path.glob("*.partial")), "left a partial behind"


# --------------------------------------------------------------------------
# The two fields the catalogue publishes and no loader read — edtech-kg#137.
# --------------------------------------------------------------------------

COURSE_PAGE = """<html><h1>Landscaping 1</h1>
<div class="field field--name-field-grades field--type-list-string">
  <div class="field__label">Grades</div>
  <div class="field__items">
    <div class="field__item">10,</div>
    <div class="field__item">11,</div>
    <div class="field__item">12</div>
  </div>
</div>
<div class="field field--name-field-description field--type-text-long field__item">
  <p>Landscaping offers skilled workers &amp; satisfying careers.</p>
</div>
<span class="field field--name-field-credits"><span class="field__item">1</span></span>
</html>"""


def test_a_course_page_yields_its_description_and_grade_levels():
    """Both are on the page and neither was read, so Q9 and Q14 returned null
    against a loaded district — the failure the schema's own block describes."""
    found = probe.parse_course(COURSE_PAGE, "https://catalog.pwcs.edu/x/y")
    assert found["grade_levels"] == ["10", "11", "12"], (
        "the catalogue writes the separator INSIDE the value — `10,` `11,` "
        "`12` — so a trailing comma survives unless it is stripped")
    assert found["description"] == (
        "Landscaping offers skilled workers & satisfying careers."), found["description"]


def test_a_field_stops_at_the_next_one_and_does_not_swallow_its_markup():
    """The stop condition, and the reason it is a SIBLING WRAPPER rather than
    the next `field--name-field-`.

    The looser stop ran past the description into whatever followed, and
    `text_of` does not strip a tag it is handed mid-attribute — so 87 of 791
    descriptions arrived carrying `<div class="field...` as text. The ENGINE
    caught it, not the parser: `lit()` refuses a string holding both quote
    characters, and those were the only descriptions holding a double quote.
    """
    found = probe.parse_course(COURSE_PAGE, "https://catalog.pwcs.edu/x/y")
    for leak in ("<div", "<span", "class=", "field__item", "Credits", "1"):
        if leak in ("1",):
            assert not found["description"].endswith("1"), "the credits field leaked in"
            continue
        assert leak not in found["description"], f"{leak!r} leaked into the description"
    assert "Grades" not in found["description"]


def test_a_page_with_neither_field_reports_absence_not_emptiness():
    """Absence is real here and common — 8 of 791 courses publish no
    description and 10 publish no grades. `None` and `[]` say so; `""` would
    make `c.description IS NOT NULL` true for every course."""
    found = probe.parse_course("<html><h1>Bare Course</h1></html>", "u")
    assert found["description"] is None
    assert found["grade_levels"] == []


def test_the_items_container_is_not_read_as_an_item():
    """`field__item` also matches inside `class="field__items"`.

    `[^>]*` absorbed the `s"`, so the CONTAINER matched first and its capture
    ran to the first `</div>` inside it. On the current template that is the
    first real item, so the answer came out right by coincidence of ordering.
    Move the label inside `field__items` — which Drupal templates do — and
    `Grades` is emitted as a grade level. Verified before the fix.
    """
    label_inside = """<html><h1>C</h1>
<div class="field field--name-field-grades">
  <div class="field__items">
    <div class="field__label">Grades</div>
    <div class="field__item">10,</div>
    <div class="field__item">11</div>
  </div>
</div></html>"""
    label_outside = label_inside.replace(
        '<div class="field__items">\n    <div class="field__label">Grades</div>',
        '<div class="field__label">Grades</div>\n  <div class="field__items">')
    for markup, where in ((label_inside, "inside"), (label_outside, "outside")):
        found = probe.parse_course(markup, "u")["grade_levels"]
        assert found == ["10", "11"], f"label {where} the container gave {found}"

