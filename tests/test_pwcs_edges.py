"""Building the edges — the arithmetic, without an engine.

`etl/pwcs_edges.py` decides WHICH edges exist and how many published rows fold
into each. It touches nothing but dictionaries, so every case here is driven
directly rather than through a loaded graph.

Split from `tests/test_load_pwcs.py` when it passed the 500-line review limit,
mirroring the split of the module it tests.
"""

from __future__ import annotations

from etl import pwcs_edges as edges_mod

# Every published page, and the courses among them. An edge resolves against
# the SECOND — the whole point of the split.
BY_PATH = {"/a/one": "https://catalog.pwcs.edu/a/one",
           "/a/two": "https://catalog.pwcs.edu/a/two",
           "/a": "https://catalog.pwcs.edu/a"}
COURSE_BY_PATH = {"/a/one": "https://catalog.pwcs.edu/a/one",
                  "/a/two": "https://catalog.pwcs.edu/a/two"}


def course(url: str, *hrefs: str) -> dict:
    return {"url": url,
            "prerequisite_links": [{"href": h, "name": "n"} for h in hrefs]}


def prerequisites(*records):
    return edges_mod.prerequisite_pairs(list(records), BY_PATH, COURSE_BY_PATH)


def pathway(url: str, *rows) -> dict:
    return {"url": url, "courses": [{"url": u, "section": s, "credits": c}
                                    for u, s, c in rows]}


def test_a_pathway_course_resolves_through_by_path():
    """This matched on `absolute(href)` while Course nodes are created from the
    sitemap URL verbatim, and the two normalise differently — `course_urls()`
    leaves `<loc>` untouched, `absolute()` strips a trailing slash. A mismatch
    writes no edge and still increments the counter."""
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one/", "First", "1"))], BY_PATH, COURSE_BY_PATH)
    assert list(edges["grouped"]) == [("https://catalog.pwcs.edu/p",
                                       "https://catalog.pwcs.edu/a/one")]


def test_a_course_in_two_sections_is_one_edge_with_both_names():
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "1"))], BY_PATH, COURSE_BY_PATH)
    assert len(edges["grouped"]) == 1
    assert edges["collapsed"] == 1
    assert next(iter(edges["grouped"].values()))["sections"] == ["First", "Second"]


def test_differing_credits_across_sections_are_counted_not_lost():
    """The section names were preserved when rows were folded and the credits
    were not — the same silent loss #77 is about."""
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "2"))], BY_PATH, COURSE_BY_PATH)
    assert edges["conflicting"] == 1


def test_a_pathway_row_naming_an_unparsed_page_is_counted():
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/node/1435", "First", "1"))], BY_PATH, COURSE_BY_PATH)
    assert edges["grouped"] == {} and edges["unlinkable"] == 1


def test_the_first_credit_value_is_kept_and_the_disagreement_is_counted():
    """A course in two sections of one pathway may carry different credits.
    The engine holds one edge, so one value survives — the FIRST, and the
    disagreement is reported rather than lost. Untested until now: the count
    was asserted and the surviving value was not, so keeping the last would
    have passed."""
    edges = edges_mod.pathway_edges([pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "2"))], BY_PATH, COURSE_BY_PATH)
    entry = next(iter(edges["grouped"].values()))
    assert entry["credits"] == "1", "the first published credit value must survive"
    assert edges["conflicting"] == 1


def test_a_pathway_row_naming_a_subject_page_writes_no_edge_and_counts_none():
    """The same off-level defect `prerequisite_pairs` was fixed for, on the
    other edge. `by_path` holds subject and pathway pages, so a row naming one
    resolved — and the statement written is `MATCH (c:Course …)`, which finds
    nothing. No edge, and the counter still incremented."""
    edges = edges_mod.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a", "First", "1"))],
        BY_PATH, COURSE_BY_PATH)
    assert edges["grouped"] == {}, "a subject page was resolved as a course"
    assert edges["off_level"] == ["https://catalog.pwcs.edu/a"], edges
    assert edges["unlinkable"] == 0, edges


def test_two_rows_in_the_same_section_are_counted_as_collapsed():
    """`collapsed` counted extra distinct SECTION NAMES, not folded rows. Two
    rows for one (pathway, course) pair in the same section contributed 0 —
    so a row could vanish into an edge with nothing reporting it, and
    `verify()` could not see the difference because `includes` is the number
    of pairs either way.

    That is the #77 failure this whole section exists to prevent, one level up.
    """
    edges = edges_mod.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "First", "1"))],
        BY_PATH, COURSE_BY_PATH)
    assert len(edges["grouped"]) == 1
    assert edges["collapsed"] == 1, (
        "two rows in one section folded into one edge and were reported as 0")
    entry = next(iter(edges["grouped"].values()))
    assert entry["rows"] == 2, entry
    assert entry["sections"] == ["First"], entry


def test_a_row_with_no_section_is_counted_as_collapsed():
    """The other case the old count missed: a row carrying no section name
    never entered `sections`, so folding it in reported 0."""
    edges = edges_mod.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", None, "1"))],
        BY_PATH, COURSE_BY_PATH)
    assert edges["collapsed"] == 1, edges
    entry = next(iter(edges["grouped"].values()))
    assert entry["rows"] == 2 and entry["sections"] == ["First"], entry


def test_three_rows_across_two_sections_count_two_collapsed():
    """`len(sections) - 1` gave 1 here, not 2 — it measures names, and the
    console line and `e.rows` are about rows."""
    edges = edges_mod.pathway_edges(
        [pathway("https://catalog.pwcs.edu/p",
                 ("https://catalog.pwcs.edu/a/one", "First", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "1"),
                 ("https://catalog.pwcs.edu/a/one", "Second", "1"))],
        BY_PATH, COURSE_BY_PATH)
    assert edges["collapsed"] == 2, edges
    entry = next(iter(edges["grouped"].values()))
    assert entry["rows"] == 3 and entry["sections"] == ["First", "Second"], entry


def test_two_links_to_the_same_course_make_one_edge():
    """An edge MERGE matches on start, type and end alone (#77), so two links
    naming the same course give two MERGEs, ONE edge, and a counter of two —
    and `verify()` then exits non-zero on a well-formed catalogue."""
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/a/one", "/a/one"))
    assert got["pairs"] == [("https://catalog.pwcs.edu/a/three",
                             "https://catalog.pwcs.edu/a/one")]
    assert got["duplicated"] == 1


def test_a_prerequisite_pointing_at_an_unparsed_page_is_counted():
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/node/1435"))
    assert got["pairs"] == [] and got["unresolved"] == 1


def test_a_prerequisite_resolves_to_the_node_key_not_the_href():
    """The key a Course node was created with, via `by_path` — not whatever
    spelling the href happened to use."""
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/a/one/"))
    assert got["pairs"][0][1] == "https://catalog.pwcs.edu/a/one"


def test_a_prerequisite_naming_a_subject_page_writes_no_edge_and_counts_none():
    """The one real defect in this branch. `by_path` holds subject and pathway
    pages too, so a prerequisite pointing at one resolved as if it were a
    course — and the statement written is `MATCH (a:Course …), (b:Course …)`
    where `b` is a `:Subject`. The MATCH finds nothing, no edge is written,
    and the counter still increments; `verify()` then reports a mismatch with
    nothing to say why.

    This is the guard `pwcs_source.read` already applies to pathway rows,
    missing on the edge the graph exists for. No link does this today — that
    is a property of this catalogue, measured, not a property of the code.
    """
    got = prerequisites(course("https://catalog.pwcs.edu/a/three", "/a"))
    assert got["pairs"] == [], "a subject page was resolved as a course"
    assert got["off_level"] == ["https://catalog.pwcs.edu/a"], got
    # And not conflated with a page that did not parse — different facts.
    assert got["unresolved"] == 0, got
