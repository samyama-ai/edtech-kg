"""Ed-Fi and CASE, and the page that compares them — #31 and #32.

No test downloads the 3.7 MB Ed-Fi specification. Every reader takes its
document text, and the fixtures are padded to clear the guards that refuse a
truncated document rather than to trip them.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import vocabularies as vocab

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "ed-fi-and-case.md"
RECORD = ROOT / "docs" / "sources" / "vocabularies-measured.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text())


def spec(*names: str, paths: int = 5, padding: int = 250) -> str:
    """An OpenAPI document declaring these schemas, plus filler."""
    filler = "".join(f"    edFi_filler{i}:\n      type: object\n"
                     for i in range(padding))
    declared = "".join(f"    {n}:\n      type: object\n" for n in names)
    # Letters only. `RESOURCE_PATH` matches `[a-zA-Z]+`, which is what the
    # real document uses, so a fixture with digits in the route name matched
    # nothing and every Ed-Fi test failed on the truncation guard instead of
    # on what it was written to check.
    routes = "".join(f"  /ed-fi/route{'x' * (i + 1)}s:\n    get: {{}}\n"
                     for i in range(paths))
    return "paths:\n" + routes + "components:\n  schemas:\n" + filler + declared


def context(*terms: str) -> str:
    return json.dumps({"@context": {t: {"@id": f"case:{t}"} for t in terms}})


CASE_TERMS = tuple(["CFDocument", "CFItem", "CFAssociation"]
                   + [f"dtThing{i}" for i in range(27)]
                   + [f"term{i}" for i in range(60)])

LICENCE_PAGE = ("<html><body><script>var x = 1;</script><p>Use of this "
                "specification to develop products or services is governed by "
                "the license with 1EdTech found on the 1EdTech website: "
                "http://www.imsglobal.org/speclicense.html</p></body></html>")


def test_only_four_space_schema_names_are_counted():
    """The same names recur as `$ref` targets and as property names.

    Searching for them anywhere reports several thousand schemas that do not
    exist. The indentation is what distinguishes a declaration from a use.
    """
    document = spec("edFi_school") + "\n        edFi_notASchema:\n"
    assert vocab.edfi_resources(document)["shapes"]["School"] == "edFi_school"
    assert vocab.edfi_resources(document)["edfi_schemas"] == 251


def test_a_truncated_specification_is_refused():
    with pytest.raises(vocab.MalformedSource, match="truncated or substituted"):
        vocab.edfi_resources(spec("edFi_school", padding=10))


def test_a_specification_with_no_resource_paths_is_refused():
    """Schemas without routes is a components file, not the API specification.

    It would report 622 schemas and 0 resources, and 0 there reads as "Ed-Fi
    exposes nothing" rather than as "this is the wrong document".
    """
    with pytest.raises(vocab.MalformedSource, match="truncated or substituted"):
        vocab.edfi_resources(spec("edFi_school", paths=0))


def test_a_shape_ed_fi_does_not_declare_comes_back_none():
    """`Course ALIGNS_TO Standard` is the one Ed-Fi has no single schema for."""
    got = vocab.edfi_resources(spec("edFi_school", "edFi_course"))["shapes"]
    assert got["School"] == "edFi_school"
    assert got["District"] is None


def test_ed_fi_reports_no_citable_uris():
    """The finding of #31, recorded as a key rather than an omission.

    A missing key reads as "not measured". `None` reads as "measured, and
    there are none" — which is the difference between an unfinished
    investigation and its result.
    """
    got = vocab.edfi_resources(spec("edFi_school"))
    assert "term_uris" in got and got["term_uris"] is None


def test_the_case_shapes_are_found_and_datatypes_counted_apart():
    """`dtCFItem` sits beside `CFItem`; counting both doubles the vocabulary."""
    got = vocab.case_terms(context(*CASE_TERMS))
    assert got["shapes"]["Standard / competency"] == "CFItem"
    assert got["shapes"]["Course ALIGNS_TO Standard"] == "CFAssociation"
    assert got["terms"] == 90 and got["datatype_entries"] == 27


def test_a_context_that_is_not_the_case_context_is_refused():
    with pytest.raises(vocab.MalformedSource, match="not that document"):
        vocab.case_terms(context("CFItem"))


def test_the_case_licence_sentence_is_read_verbatim():
    got = vocab.case_licence(LICENCE_PAGE)
    assert got["governs_product_use"].startswith("Use of this specification")
    assert got["spdx"] is None


def test_a_page_without_the_licence_sentence_is_refused():
    """A blank here reads as "no restriction found".

    CASE is the one of the three that has a restriction, so that is the most
    dangerous way for this reader to fail.
    """
    damaged = LICENCE_PAGE.replace("governed by", "REMOVED")
    assert damaged != LICENCE_PAGE
    with pytest.raises(vocab.MalformedSource, match="no restriction found"):
        vocab.case_licence(damaged)


def test_the_comparison_table_states_what_the_record_measured(record):
    """Both directions on the two rows that decide #69.

    The table is the deliverable — three verdicts filed separately would not
    decide anything — so it is checked against the record rather than read.
    """
    page = PAGE.read_text()
    for shape, name in record["ed_fi"]["shapes"].items():
        if name:
            assert f"`{name}`" in page, f"{shape} measured but not on the page"
    for shape, name in record["case"]["shapes"].items():
        if name:
            assert f"`{name}`" in page, f"{shape} measured but not on the page"
    assert f"**{record['ed_fi']['edfi_schemas']} `edFi_` schemas" in page
    assert f"**{record['case']['terms']} terms**" in page
    assert f"Measured **{record['retrieved_at']}**" in page

    # The comparison row that carries #31's whole answer. Changing "none" to
    # "yes" in that cell left every assertion above green, and the table is
    # the part a reader of #69 acts on.
    row = re.search(r"^\| \*\*Citable term URIs\*\* \|([^|]*)\|([^|]*)\|",
                    page, re.M)
    assert row, "the page no longer compares citable term URIs"
    ed_fi_cell = row.group(2).strip()
    assert (ed_fi_cell == "**none**") == (record["ed_fi"]["term_uris"] is None)


def test_the_page_quotes_the_licence_sentence_the_record_holds(record):
    # Blockquote markers stripped BEFORE whitespace is squashed. A markdown
    # quote wraps, so `> ` lands in the middle of the sentence and a
    # substring test fails for a reason that has nothing to do with the text.
    page = re.sub(r"\s+", " ", re.sub(r"(?m)^> ", "", PAGE.read_text()))
    quoted = record["case"]["licence"]["governs_product_use"]
    # The page stops the quote before the bare URL, which renders as a link
    # and is not part of the sentence being relied on.
    assert quoted.split(" found on")[0] in page


def test_the_page_does_not_claim_fifty_states_publish_case():
    """#32's title says "already machine-readable" and this did not confirm it.

    One state endpoint was tried and did not resolve. A page that read as a
    census would answer #69 on a count nobody made.
    """
    page = re.sub(r"\s+", " ", PAGE.read_text().lower())
    assert "that all 50 states publish their standards as case" in page
    assert "nothing here supports a count" in page
