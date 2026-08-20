"""Writing the catalogue — the edges, and the schema they must agree with.

Every write is a MERGE, because a constraint in 1.1.0 declares the key and does
not reject a duplicate CREATE. The two edge-building steps are pure functions
so the grouping and the collapse arithmetic can be checked without an engine.

The engine client is `tests/test_engine.py`; the parsing is
`tests/test_pwcs_source.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etl import load_pwcs as loader
from etl import pwcs_source as reader
from etl.engine import Unquotable

CACHE = Path(__file__).resolve().parents[1] / "data" / "pwcs"

# `read()` walks 960 pages. Cached they are local and instant; cold it is 960
# requests to a school district from a test run. `data/` is gitignored, so a
# fresh clone has none of it, and these would hammer the source rather than
# fail. Skipped instead — with the command that makes them runnable.
needs_cache = pytest.mark.skipif(
    not CACHE.exists() or not any(CACHE.iterdir()),
    reason="no cached catalogue in data/pwcs — run `python -m etl.probe_pwcs` first")

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
    """Which label the loader upserts on which property.

    `re.DOTALL` on the argument list: the previous pattern matched only a
    single-line call, so wrapping one across lines dropped that label from the
    schema-agreement check silently — a guard quietly covering less than it
    claimed.
    """
    import inspect
    import re
    return dict(re.findall(r'upsert\(\s*engine,\s*"(\w+)",\s*"(\w+)"',
                           inspect.getsource(loader), re.S))


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
    the property unset even when the two names agree.

    Asserted by CALLING it, not by matching a fragment of its source. The
    previous version pinned an exact f-string and broke on any reformat, while
    proving nothing about what upsert emits.
    """
    sent = []

    class Recorder:
        def run(self, query):
            sent.append(query)

    loader.upsert(Recorder(), "Course", "url", "https://x/y", {"name": "A"})
    assert sent[0] == "MERGE (n:Course {url: 'https://x/y'})", sent[0]
    assert sent[1] == ("MATCH (n:Course {url: 'https://x/y'}) SET n.name = 'A'"), sent[1]


def test_upsert_refuses_a_label_or_property_that_is_not_an_identifier():
    """`lit()` guards values. Labels and property names are interpolated bare —
    Cypher has no other way to write them — so nothing guarded them at all.
    Every name here is a source literal today; the next loader may build one
    from a column heading."""
    class Recorder:
        def run(self, query):
            raise AssertionError(f"should not have run: {query}")

    for label, key, props in (("Cour se", "url", {}),
                              ("Course", "n.url", {}),
                              ("Course", "url", {"na me": "x"})):
        with pytest.raises(Unquotable):
            loader.upsert(Recorder(), label, key, "v", props)


# --------------------------------------------------------------------------
# building the edges — the arithmetic, without an engine
# --------------------------------------------------------------------------

BY_PATH = {"/a/one": "https://catalog.pwcs.edu/a/one",
           "/a/two": "https://catalog.pwcs.edu/a/two"}


def course(url: str, *hrefs: str) -> dict:
    return {"url": url,
            "prerequisite_links": [{"href": h, "name": "n"} for h in hrefs]}


def test_two_links_to_the_same_course_make_one_edge():
    """An edge MERGE matches on start, type and end alone (#77), so two links
    naming the same course give two MERGEs, ONE edge, and a counter of two —
    and `verify()` then exits non-zero on a well-formed catalogue."""
    got = loader.prerequisite_pairs(
        [course("https://catalog.pwcs.edu/a/three", "/a/one", "/a/one")], BY_PATH)
    assert got["pairs"] == [("https://catalog.pwcs.edu/a/three",
                             "https://catalog.pwcs.edu/a/one")]
    assert got["duplicated"] == 1


def test_a_prerequisite_pointing_at_an_unparsed_page_is_counted():
    got = loader.prerequisite_pairs(
        [course("https://catalog.pwcs.edu/a/three", "/node/1435")], BY_PATH)
    assert got["pairs"] == [] and got["unresolved"] == 1


def test_a_prerequisite_resolves_to_the_node_key_not_the_href():
    """The key a Course node was created with, via `by_path` — not whatever
    spelling the href happened to use."""
    got = loader.prerequisite_pairs(
        [course("https://catalog.pwcs.edu/a/three", "/a/one/")], BY_PATH)
    assert got["pairs"][0][1] == "https://catalog.pwcs.edu/a/one"


def pathway(url: str, *rows) -> dict:
    return {"url": url, "courses": [{"url": u, "section": s, "credits": c}
                                    for u, s, c in rows]}


def test_a_pathway_course_resolves_through_by_path():
    """This matched on `absolute(href)` while Course nodes are created from the
    sitemap URL verbatim, and the two normalise differently — `course_urls()`
    leaves `<loc>` untouched, `absolute()` strips a trailing slash. A mismatch
    writes no edge and still increments the counter."""
    edges = loader.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one/", "First", "1"))], BY_PATH)
    assert list(edges["grouped"]) == [("https://catalog.pwcs.edu/p",
                                       "https://catalog.pwcs.edu/a/one")]


def test_a_course_in_two_sections_is_one_edge_with_both_names():
    edges = loader.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "1"))], BY_PATH)
    assert len(edges["grouped"]) == 1
    assert edges["collapsed"] == 1
    assert next(iter(edges["grouped"].values()))["sections"] == ["First", "Second"]


def test_differing_credits_across_sections_are_counted_not_lost():
    """The section names were preserved when rows were folded and the credits
    were not — the same silent loss #77 is about."""
    edges = loader.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "2"))], BY_PATH)
    assert edges["conflicting"] == 1


def test_a_pathway_row_naming_an_unparsed_page_is_counted():
    edges = loader.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/node/1435", "First", "1"))], BY_PATH)
    assert edges["grouped"] == {} and edges["unlinkable"] == 1


def test_apply_schema_does_not_truncate_a_statement_carrying_a_url(tmp_path):
    """`apply_schema` stripped comments by splitting on `//`, which cuts
    `MERGE (n {url: 'https://x'})` at the scheme. No schema statement carries a
    URL today — they are all in comments — which is the only reason the naive
    split never did damage."""
    schema = tmp_path / "s.cypher"
    schema.write_text("// a comment mentioning https://example.org\n"
                      "CREATE CONSTRAINT ON (c:C) ASSERT c.url IS UNIQUE;  // key\n"
                      "MERGE (n:C {url: 'https://example.org/x'});\n")
    sent = []

    class Recorder:
        def run(self, query):
            sent.append(query)

    loader.apply_schema(Recorder(), quiet=True, schema=schema)
    assert sent == ["CREATE CONSTRAINT ON (c:C) ASSERT c.url IS UNIQUE",
                    "MERGE (n:C {url: 'https://example.org/x'})"], sent
