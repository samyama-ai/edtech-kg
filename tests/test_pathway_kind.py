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

from etl.pwcs_pages import PATHWAY_KINDS, kind_of

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


def test_every_kind_written_is_one_the_vocabulary_names():
    """No third value can appear without being declared here first."""
    assert set(PATHWAY_KINDS.values()) == {"career pathway",
                                           "specialty program"}
