"""`Pathway.kind` is read from the catalogue, never inferred.

#156. The loader used to write

    kind = "career pathway" if "career-pathways" in url else "specialty program"

and the `else` is the defect. "specialty program" was not a classification, it
was a **residue** — everything that was not a career pathway, whatever it
actually was.

Measured over the 42 loaded pathways: 16 pages state `career-pathways`, 25
state `specialty-programs`, and one states neither. That one is Virtual Prince
William, a virtual school which is neither, and it was being written as a
specialty program — a fact the district does not publish.

One wrong label is small. The `else` is not: it answers for every page the
catalogue has not published yet, confidently, and the count stays plausible
whatever arrives.
"""

import pytest

from etl import load_pwcs as loader
from etl.pwcs_pages import PATHWAY_KINDS, kind_of
from tests.test_load_pwcs import Recorder

CATALOGUE = "https://catalog.pwcs.edu"


@pytest.mark.parametrize("path, expected", [
    # The two the catalogue states, each in the shape it publishes them.
    ("/career-and-technical-education-cte/career-pathways/health-science.html",
     "career pathway"),
    ("/military-science-jrotc/career-pathways/government-public.html",
     "career pathway"),
    ("/specialty-programs/international-baccalaureate.html",
     "specialty program"),
    ("/governors-school/specialty-programs/innovation-park.html",
     "specialty program"),
    ("/career-and-technical-education-cte/specialty-programs/welding.html",
     "specialty program"),
])
def test_a_stated_kind_is_read_from_the_path(path, expected):
    assert kind_of(CATALOGUE + path) == expected


def test_the_page_stating_neither_gets_no_kind_at_all():
    """The real page this issue was raised for.

    Virtual Prince William is a virtual school. It is not a career pathway and
    it is not a specialty program, and the catalogue says so by putting it
    under neither section. `None` means the loader omits the property — an
    absent key is visible to any query that asks for it; a wrong one is not.
    """
    assert kind_of(CATALOGUE
                   + "/virtual-prince-william/"
                     "virtual-prince-william-information.html") is None


@pytest.mark.parametrize("path", [
    "/",
    "/some-new-section/a-page-nobody-has-published-yet.html",
    "/career-and-technical-education/whatever.html",   # near-miss segment
])
def test_a_section_the_catalogue_has_not_published_gets_no_kind(path):
    """What would this report in a case the current data does not contain?

    Under the old rule: "specialty program", confidently, forever. That is the
    question this repo asks of every counter, and it is the one the `else`
    failed.
    """
    assert kind_of(CATALOGUE + path) is None


def test_the_marker_is_a_whole_segment_not_a_substring():
    """Substring matching would be looser than the evidence.

    A page NAMED for career pathways is not a page the district PLACED in that
    section, and only the placement is the district's own classification.
    """
    assert kind_of(CATALOGUE
                   + "/specialty-programs/welding-career-pathways-overview.html"
                   ) == "specialty program"
    assert kind_of(CATALOGUE + "/guides/about-career-pathways.html") is None


def test_two_markers_are_refused_rather_than_resolved():
    """No page does this today. If one appears, the district is contradicting
    itself and picking a winner would hide that."""
    assert kind_of(CATALOGUE
                   + "/career-pathways/specialty-programs/x.html") is None


def test_the_vocabulary_is_the_districts_words_not_ours():
    """The keys are path segments the catalogue publishes; the values are the
    prose the graph stores. A test so that renaming either half is deliberate.
    """
    assert PATHWAY_KINDS == {"career-pathways": "career pathway",
                             "specialty-programs": "specialty program"}


def loaded_pathway(url: str, title: str = "A Pathway") -> str:
    """The Cypher `load()` writes for one pathway, through the real upsert.

    Driven through `load()` rather than asserted on `kind_of`, because the
    helper being right does not make the LOADER right — a mutation putting
    `kind or "specialty program"` back at the call site left every test about
    `kind_of` green. The claim is about what reaches the graph, so the test
    has to read what reaches the graph.
    """
    engine = Recorder()
    loader.load(engine, {"published": set(), "subjects": [], "courses": [],
                         "pathways": [{"url": url, "title": title,
                                       "courses": [], "dangling": []}]},
                quiet=True)
    return "\n".join(engine.sent)


def test_a_stated_kind_reaches_the_graph():
    written = loaded_pathway(CATALOGUE + "/x/career-pathways/health.html")
    assert "career pathway" in written


def test_an_unstated_kind_is_omitted_from_the_write_entirely():
    """Not written as null, not written as a default — ABSENT.

    This is the assertion the mutation `properties["kind"] = kind or
    "specialty program"` has to fail, and the one that was missing.
    """
    written = loaded_pathway(
        CATALOGUE + "/virtual-prince-william/virtual-prince-william-info.html")
    assert "Pathway" in written, "the pathway itself must still be written"
    assert "kind" not in written, (
        "the loader wrote a kind the catalogue does not publish:\n" + written)
    assert "specialty program" not in written


def counted(printed: str) -> dict[str, int]:
    """The figures off the loader's own output lines.

    Parsed rather than substring-matched. `printed.count("1") >= 3` was the
    first version and it counts the CHARACTER `1` anywhere in stdout — subject
    counts, course counts, any number containing a one. It would pass with all
    three pathways miscounted, while carrying the claim that the printed counts
    are the written counts.
    """
    figures = {}
    for line in printed.splitlines():
        for label in ("career pathway", "specialty program", "kind unstated",
                      "kind contradictory"):
            if line.strip().startswith(label):
                figures[label] = int(line.strip()[len(label):].replace(",", ""))
    return figures


def test_the_loader_counts_what_it_wrote_including_the_unstated(capsys):
    """The counts printed are the counts written, not the counts planned.

    A loader reporting a split it did not write is the same defect one level
    up, and this repo has hit it before — `pages_read` reported the pages
    PLANNED, and a document quoted a reach the run never had.
    """
    engine = Recorder()
    loader.load(engine, {"published": set(), "subjects": [], "courses": [],
                         "pathways": [
                             {"url": CATALOGUE + "/a/career-pathways/x.html",
                              "title": "One", "courses": [], "dangling": []},
                             {"url": CATALOGUE + "/b/specialty-programs/y.html",
                              "title": "Two", "courses": [], "dangling": []},
                             {"url": CATALOGUE + "/nowhere/z.html",
                              "title": "Three", "courses": [], "dangling": []}]},
                quiet=False)
    printed = capsys.readouterr().out

    assert counted(printed) == {"career pathway": 1, "specialty program": 1,
                                "kind unstated": 1}, printed
    # And what was printed is what was sent — the two records of one fact.
    written = "\n".join(engine.sent)
    assert written.count("career pathway") == 1
    assert written.count("specialty program") == 1


def test_the_counts_are_read_off_the_lines_and_not_from_stray_digits():
    """`counted` is load-bearing, so it is tested rather than trusted.

    A parser that returned {} would make the assertion above compare {} to a
    dict and fail loudly — but one that matched the wrong line would not.
    """
    printed = ("  courses      791\n"
               "  pathways      42\n"
               "    career pathway        16\n"
               "    specialty program     25\n"
               "    kind unstated          1\n")
    assert counted(printed) == {"career pathway": 16, "specialty program": 25,
                                "kind unstated": 1}


def test_a_page_naming_two_sections_is_counted_apart_from_silence(capsys):
    """A district contradicting itself must not read as a district saying
    nothing. Both leave `kind` absent; they are not the same fact."""
    engine = Recorder()
    loader.load(engine, {"published": set(), "subjects": [], "courses": [],
                         "pathways": [
                             {"url": CATALOGUE
                              + "/career-pathways/specialty-programs/x.html",
                              "title": "Both", "courses": [], "dangling": []},
                             {"url": CATALOGUE + "/nowhere/z.html",
                              "title": "Neither", "courses": [],
                              "dangling": []}]},
                quiet=False)
    figures = counted(capsys.readouterr().out)
    assert figures == {"kind unstated": 1, "kind contradictory": 1}
