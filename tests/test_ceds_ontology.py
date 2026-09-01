"""What CEDS defines, and the page that reports it — edtech-kg#29.

No test downloads the 20 MB ontology. Every reader takes the RDF text, so the
suite hands it a fixture built to be just large enough to pass the guard that
refuses a truncated document.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import ceds_ontology as ceds

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "ceds.md"
RECORD = ROOT / "docs" / "sources" / "ceds-measured.json"

NS = "https://w3id.org/CEDStandards/terms/"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text())


def block(tag: str, identifier: str, label: str) -> str:
    return (f'<{tag} rdf:about="{NS}{identifier}">'
            f"<rdfs:label>{label}</rdfs:label></{tag}>")


def ontology(*pairs: tuple[str, str], tag: str = "owl:Class",
             padding: int = 600) -> str:
    """An RDF document holding these classes, plus filler to clear the guard.

    The filler is real class blocks rather than whitespace: `classes()` refuses
    on the COUNT it finds, so padding with anything it does not count would
    make every fixture here trip the guard rather than exercise the reader.
    """
    filler = "".join(block(tag, f"C90{i:04d}", f"Filler {i}") for i in range(padding))
    return "<rdf:RDF>" + filler + "".join(
        block(tag, i, l) for i, l in pairs) + "</rdf:RDF>"


def test_both_class_forms_are_read():
    """404 of the 1,369 are `rdfs:Class` and the rest are `owl:Class`.

    Reading one form gives 965 and no sign that the others exist — an
    undercount that reads as a finding about the vocabulary's size.
    """
    rdf = (ontology(("C200072", "Course"))
           + ontology(("C200199", "K12 School"), tag="rdfs:Class"))
    found = ceds.classes(rdf)
    assert found["C200072"] == "Course"
    assert found["C200199"] == "K12 School"


def test_a_truncated_download_is_refused_not_reported():
    """A half-written 20 MB file parses and reports a smaller vocabulary.

    That number would be published as "CEDS defines fewer terms than
    expected", which is why the guard is on the count rather than on zero.
    """
    with pytest.raises(ceds.MalformedSource, match="truncated or substituted"):
        ceds.classes(ontology(("C200072", "Course"), padding=10))


def test_a_class_without_a_label_is_not_counted():
    """The label IS the name. A class with none cannot be cited by one."""
    rdf = ontology(("C200072", "Course")).replace(
        f'<owl:Class rdf:about="{NS}C900001"><rdfs:label>Filler 1</rdfs:label>',
        f'<owl:Class rdf:about="{NS}C900001">')
    assert "C900001" not in ceds.classes(rdf)


def test_classes_outside_the_ceds_namespace_are_not_counted():
    """The document imports OWL's own vocabulary.

    Counting `owl:Class` itself as a CEDS term inflates the total by whatever
    the ontology happens to import.
    """
    rdf = ontology(("C200072", "Course")).replace(
        "</rdf:RDF>",
        '<owl:Class rdf:about="http://www.w3.org/2002/07/owl#Class">'
        "<rdfs:label>Class</rdfs:label></owl:Class></rdf:RDF>")
    assert "Class" not in ceds.classes(rdf).values()


def test_a_shape_ceds_does_not_define_comes_back_none():
    """`None`, not a missing key.

    An absent key and a key with no match read identically to a caller, and
    "CEDS has no term for this" is the answer that decides mint over align.
    """
    found = ceds.classes(ontology(("C200072", "Course")))
    got = ceds.shapes(found, {"Course": "Course", "Timetable": "Timetable"})
    assert got["Course"]["ceds_id"] == "C200072"
    assert got["Timetable"] == {"ceds_label": "Timetable", "ceds_id": None,
                                "uri": None}


def test_the_uri_is_built_from_the_identifier_not_the_label():
    """The whole finding. `Course` is `C200072`, and the URI carries the
    number rather than the word."""
    found = ceds.classes(ontology(("C200072", "Course")))
    assert ceds.shapes(found, {"Course": "Course"})["Course"]["uri"] == \
        NS + "C200072"


def test_label_uniqueness_is_measured_as_two_numbers():
    """Reported as a pair so the page cannot claim uniqueness on one figure.

    If labels collided, citing CEDS by label would be ambiguous and the opaque
    identifier would be the only safe citation.
    """
    found = ceds.classes(ontology(("C200072", "Course"), ("C200073", "Course")))
    counted = ceds.unique_labels(found)
    assert counted["classes"] == 602 and counted["distinct_labels"] == 601


def test_the_page_states_the_identifier_the_record_holds(record):
    """Both directions on the shape table.

    Keyed on the CEDS LABEL column, not on our own shape names: those carry
    backticks and slashes on the page and the identifier is what has to match.
    """
    rows = dict(re.findall(r"^\|[^|]+\| ([A-Za-z0-9 ]+?) \| `(C\d+)` \|$",
                           PAGE.read_text(), re.M))
    assert rows, "the page no longer carries the shape table"
    for shape, one in record["shapes"].items():
        label = one["ceds_label"]
        assert label in rows, f"{shape} ({label}) is measured but not on the page"
        assert rows[label] == one["ceds_id"], f"{shape} identifier differs"
    assert set(rows.values()) == {one["ceds_id"] for one in record["shapes"].values()}


def test_the_page_states_the_counts_and_licence_the_record_holds(record):
    page = re.sub(r"\s+", " ", PAGE.read_text())
    assert f"**{record['classes']:,}**" in page
    assert f"**{record['distinct_labels']:,}**" in page
    assert f"**{record['licence']}**" in page
    assert f"**{record['bytes']:,} bytes**" in page
    assert f"Measured **{record['retrieved_at']}**" in page


def test_the_page_does_not_claim_publishers_use_ceds():
    """#53's lesson, and the thing this investigation cannot answer.

    A page that reads as "CEDS is adopted" would decide #69's rows on evidence
    nobody gathered.
    """
    page = re.sub(r"\s+", " ", PAGE.read_text().lower())
    assert "whether anyone publishes ceds" in page
    assert "it is deliberately not answered by guessing" in page
    assert "#69 stays open" in page
