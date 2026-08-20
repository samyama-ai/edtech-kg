"""Tests for the district loader.

No engine. Everything here is a pure function or a parse, and the parts that
need a graph are covered by the loader's own read-back verification — which
exits non-zero when what it wrote and what the engine holds disagree.

Three of these guard defects the loader shipped with and a review found:

  * `lit()` is called "the whole of the defence" and had no test at all
  * `parse_pathway` found 71 of 218 rows in its first version, because a
    pathway publishes several course lists and the bound stopped at the first
  * every resolution loop indexed `by_path` after testing `published`, two
    different sets, so a sitemap page that failed to parse raised KeyError
    mid-load rather than being counted
"""

from __future__ import annotations

import pytest

from etl import load_pwcs as loader


# --------------------------------------------------------------------------
# lit() — 1.1.0 has no escape sequence, so the quote choice IS the defence
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("plain", "'plain'"),
    ("Governor's School", '"Governor\'s School"'),
    ('say "hi"', "'say \"hi\"'"),
    ("back\\slash", "'back\\slash'"),
    (None, "null"),
    (True, "true"),
    (False, "false"),
    (3, "3"),
    (1.5, "1.5"),
])
def test_a_value_is_wrapped_in_the_quote_it_does_not_contain(value, expected):
    assert loader.lit(value) == expected


def test_a_value_holding_both_quotes_is_refused_not_mangled():
    """1.1.0 supports no escape sequence inside a string literal — not `\\'`,
    not `''`, not `\\"` — so a value containing both quote characters cannot be
    expressed at all, and `/api/query` takes no parameters to fall back on.

    Raising is the point. A course silently loaded under a different name than
    the district published is the failure nothing downstream would show.
    """
    with pytest.raises(loader.Unquotable):
        loader.lit("""Governor's "School\"""")


def test_a_quote_cannot_terminate_the_literal_early():
    """The property being defended: whatever wrapper is chosen, the value does
    not contain it, so nothing can close the string early."""
    for value in ("O'Brien", 'the "best" course', "plain"):
        rendered = loader.lit(value)
        assert rendered[0] == rendered[-1], rendered
        assert rendered[0] not in value, rendered


def test_no_value_in_this_catalogue_is_unquotable():
    """Stated as a measurement rather than a hope — if a future catalogue
    breaks it, this says so rather than the loader raising mid-run."""
    data = loader.read()
    for record in data["subjects"] + data["courses"] + data["pathways"]:
        for value in (record["url"], record["title"], record.get("requirements_text")):
            if value:
                loader.lit(value)


# --------------------------------------------------------------------------
# keys
# --------------------------------------------------------------------------

def test_a_requirement_id_is_stable():
    same = (loader.requirement_id("https://a/x", "Teacher recommendation"),
            loader.requirement_id("https://a/x", "Teacher  recommendation\n"))
    assert same[0] == same[1], "whitespace should normalise, so a re-run MERGEs"


def test_two_districts_sharing_a_path_get_different_requirement_ids():
    """The defect 577975e fixed, asserted rather than remembered: the id was
    derived from the course PATH, and a path does not carry the district."""
    a = loader.requirement_id("https://one.edu/maths/algebra-1", "Teacher recommendation")
    b = loader.requirement_id("https://two.edu/maths/algebra-1", "Teacher recommendation")
    assert a != b


def test_an_href_becomes_the_absolute_url_the_key_is_built_on():
    assert loader.absolute("/art/1") == "https://catalog.pwcs.edu/art/1"
    assert loader.absolute("/art/1/") == "https://catalog.pwcs.edu/art/1", "trailing slash"
    assert loader.absolute("/art/1#top") == "https://catalog.pwcs.edu/art/1", "fragment"


def test_segments_counts_the_catalogue_levels():
    assert loader.segments("https://catalog.pwcs.edu/band") == ["band"]
    assert loader.segments("https://catalog.pwcs.edu/band/concert") == ["band", "concert"]


# --------------------------------------------------------------------------
# parse_pathway — the parse that got it wrong the first time
# --------------------------------------------------------------------------

def row(path: str, credits: str = "1") -> str:
    return (f'<article about="{path}" class="node row degree-row">'
            f'<div class="col-10"><a href="{path}">A course</a></div>'
            f'<span class="field field--name-field-credits field__item">{credits}</span>'
            f'</article>')


def section(title: str, *paths: str) -> str:
    return (f'<h2 class="field field--name-field-degree-section-title '
            f'field__item">{title}</h2>'
            f'<div class="field field--name-field-degree-section-courses">'
            + "".join(row(p) for p in paths) + "</div>")


PUBLISHED = {"/a/one", "/a/two", "/b/three"}


def test_rows_are_read_from_every_section_not_only_the_first():
    """The defect: a pathway publishes SEVERAL course lists, one per named
    section, and the first version bounded the enclosing field with a lookahead
    that stopped at the first — 71 of 218 rows. A partial parse returning
    plausible numbers is the failure this repo keeps hitting."""
    markup = section("First", "/a/one") + section("Second", "/a/two", "/b/three")
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert len(got["courses"]) == 3, got["courses"]


def test_each_row_is_attributed_to_the_section_it_sits_under():
    markup = section("First", "/a/one") + section("Second", "/a/two")
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert {c["url"].rsplit("/", 2)[-2] + "/" + c["url"].rsplit("/", 1)[-1]: c["section"]
            for c in got["courses"]} == {"a/one": "First", "a/two": "Second"}


def test_a_row_before_any_section_title_has_no_section():
    got = loader.parse_pathway(
        f'<div class="field field--name-field-degree-section-courses">{row("/a/one")}</div>',
        "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["section"] is None


def test_a_section_title_is_unescaped():
    markup = section("Journalism &amp; Broadcasting", "/a/one")
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["courses"][0]["section"] == "Journalism & Broadcasting"


def test_a_row_pointing_outside_the_sitemap_is_reported_not_dropped():
    """Five of 202 real rows point at a Drupal node id with no published alias.
    Counting them as absent would understate what the district publishes."""
    markup = section("First", "/a/one", "/node/1435")
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert len(got["courses"]) == 1
    assert got["dangling"] == ["/node/1435"]


def test_a_rendered_field_with_no_rows_is_a_parse_failure_not_an_empty_pathway():
    """The same distinction the probe draws for the prerequisite field: the
    field would not be rendered at all if there were nothing in it."""
    markup = '<div class="field field--name-field-degree-section-courses"></div>'
    got = loader.parse_pathway(markup, "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["field_present_no_rows"] is True


def test_a_pathway_with_no_such_field_is_not_a_parse_failure():
    got = loader.parse_pathway("<html></html>", "https://catalog.pwcs.edu/p", PUBLISHED)
    assert got["field_present_no_rows"] is False
    assert got["courses"] == []


# --------------------------------------------------------------------------
# what the catalogue actually holds — read from the cache, not asserted
# --------------------------------------------------------------------------

def test_the_three_levels_account_for_every_sitemap_page():
    """795 courses, 127 subjects, 38 pathways. The probe reports all 960 as
    courses (#74); the split has to add up or one of the three is wrong."""
    data = loader.read()
    total = len(data["subjects"]) + len(data["courses"]) + len(data["pathways"])
    assert total == len(data["urls"]), (
        f"{len(data['urls'])} pages in the sitemap, {total} classified")
    assert (len(data["subjects"]), len(data["courses"]), len(data["pathways"])) \
        == (127, 795, 38)


def test_no_prerequisite_crosses_out_of_the_course_level():
    """The claim #74 rests on: reclassifying 165 pages does not touch the 240
    edges, because no page outside the 795 is at either end of one."""
    data = loader.read()
    for record in data["subjects"] + data["pathways"]:
        assert not record["prerequisite_links"], record["url"]
    depths = {len(loader.segments(link["href"]))
              for r in data["courses"] for link in r["prerequisite_links"]}
    assert depths <= {2}, f"a prerequisite points outside the course level: {depths}"


# --------------------------------------------------------------------------
# the loader and the schema must agree on the key
# --------------------------------------------------------------------------

def declared_keys() -> dict[str, str]:
    import re
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "schema" / "edtech_kg.cypher").read_text()
    code = "\n".join(line.split("//")[0] for line in text.splitlines())
    return dict((label, key) for label, key in
                re.findall(r"CREATE CONSTRAINT ON \(\w+:(\w+)\) ASSERT \w+\.(\w+) IS UNIQUE", code))


def loader_keys() -> dict[str, str]:
    import inspect
    import re
    return dict((label, key) for label, key in
                re.findall(r'upsert\(engine, "(\w+)", "(\w+)"', inspect.getsource(loader)))


def test_every_label_the_loader_writes_is_keyed_as_the_schema_declares():
    """`Pathway` was declared `ASSERT pw.ctid IS UNIQUE` while the loader
    upserted on `url` and never set `ctid`. All 38 nodes carried a null value
    for the declared key, and 1.1.0 accepted it in silence — a constraint here
    declares the key and does not enforce it, which is the whole reason the
    schema tells loaders to MERGE.

    Reading both sides rather than restating either, so this cannot drift.
    """
    declared, used = declared_keys(), loader_keys()
    assert used, "no upsert calls found — did the loader change shape?"
    for label, key in used.items():
        assert label in declared, f"{label} is written but declared nowhere"
        assert declared[label] == key, (
            f"the loader keys {label} on {key!r}; the schema declares "
            f"{declared[label]!r}. Every node would carry a null declared key.")


def test_the_loader_sets_the_key_it_merges_on():
    """The other half: a key the loader MERGEs on but never writes would leave
    the property unset even when the two names agree."""
    import inspect
    source = inspect.getsource(loader.upsert)
    assert "{{{key}: {lit(value)}}}" in source, \
        "upsert no longer writes the key into the MERGE pattern"
