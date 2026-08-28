"""The Registry's data licence, and the page that reports it — edtech-kg#56.

Nothing here fetches. Every reader in `etl.registry_licence` takes its input,
so the suite hands it fixtures; the live sources are read when a person runs
`python -m etl.registry_licence`.

The document is checked against `docs/sources/registry-licence-measured.json`
in both directions. One direction alone lets an invented quote sit on the page
unchallenged, and on this page a quote that drifts is a claim about what this
project may lawfully do.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import registry_licence as rl

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "registry-data-licence.md"
RECORD = ROOT / "docs" / "sources" / "registry-licence-measured.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text())


TERMS_PAGE = """<html><body><script>var x = "license to do anything";</script>
<h2>License and Use</h2>
<p>Users: Subject to your compliance with these Terms, Credential Engine grants
you a personal, limited, revocable, nonexclusive, and nontransferable license to
view, access, and use the Websites and the Credential Registry, solely for your
personal use and internal use within your organization.</p>
<p>You may not reproduce, publish, distribute, display, modify, create
derivative works from, sell in any way, in whole or in part, or make commercial
use of the Credential Registry or any content on the Websites without the
separate prior consent of Credential Engine.</p>
<p>Developers: Entities that either: (i) develop software applications that
access and use data from the Websites and the Credential Registry; or (ii)
aggregate, publish, transmit or otherwise reproduce, transfer, distribute or
disseminate data from the Websites and the Credential Registry to third
parties, whether for commercial or noncommercial purposes; must in addition to
these Terms of Use agree to and sign our Developer Agreement.</p>
</body></html>"""

VOCABULARY = [
    {"@id": "ceterms:Course"}, {"@id": "ceterms:name"},
    {"@id": "ceterms:prerequisite"}, {"@id": "ceterms:License"},
    {"@id": "ceterms:RightsAction"}, {"@id": "ceterms:copyrightHolder"},
    {"@id": "ceterms:rightSource"},
    # A real CTDL term whose LOCAL name carries "terms" and which is still not
    # a data licence — the conditions under which an agreement ends.
    {"@id": "statementCat:TerminationTerms"},
]


def envelope(*fields: str) -> dict:
    return {"decoded_resource": {"@graph": [
        {"@type": "ceterms:Course", **{f: "x" for f in fields}}]}}


def test_the_three_sentences_the_conclusion_rests_on_are_read():
    read = rl.terms_of_use(TERMS_PAGE)
    assert "solely for your personal use" in read["grant"]
    assert read["restriction"].startswith("You may not reproduce")
    assert "noncommercial purposes" in read["developer_agreement"]


def test_inline_script_is_not_read_as_terms():
    """The fixture's script says "license to do anything".

    Strip the tags before the scripts and it survives as prose, on a page
    whose whole subject is what a licence permits.
    """
    assert "license to do anything" not in rl.flatten(TERMS_PAGE)


@pytest.mark.parametrize("missing", [
    "nontransferable license", "You may not reproduce", "Developer Agreement"])
def test_a_page_missing_any_of_the_three_is_refused(missing):
    """`match=` on each: a bare `raises` passes when a DIFFERENT guard fires.

    A blank here would read as "no restriction found", which is the most
    dangerous possible way for this module to fail.

    The first assertion is that the REMOVAL HAPPENED. It did not, on the first
    version: the phrase chosen spanned a line break in the fixture, `replace`
    matched nothing, and the test passed against a page with all three
    sentences intact — a refusal test that never presented anything to refuse.
    """
    damaged = TERMS_PAGE.replace(missing, "REMOVED")
    assert damaged != TERMS_PAGE, f"{missing!r} is not in the fixture as written"
    with pytest.raises(rl.MalformedSource, match="Refusing rather than"):
        rl.terms_of_use(damaged)


def test_the_prefix_is_stripped_before_the_vocabulary_is_searched():
    """Every CTDL term is named `ceterms:something`, and "terms" is searched for.

    A property called `termsOfUse` is precisely what #56 asks whether CTDL
    has, so the word stays in the pattern — which means searching the raw
    identifiers matches all 1,032 terms. That is how a first pass reported a
    vocabulary full of licensing properties.
    """
    assert rl.rights_terms_in(VOCABULARY) == [
        "ceterms:License", "ceterms:RightsAction", "ceterms:copyrightHolder",
        "ceterms:rightSource", "statementCat:TerminationTerms"]


def test_a_vocabulary_with_no_rights_term_is_refused():
    """`ceterms:copyrightHolder` is published, so zero means it did not load."""
    with pytest.raises(rl.MalformedSource, match="did not load"):
        rl.rights_terms_in([{"@id": "ceterms:Course"}])


def test_only_copyright_holder_counts_as_a_record_saying_something():
    """`ceterms:License` on a record is a CREDENTIAL type, not a data licence.

    Counting it would turn every published professional licence into evidence
    that publishers licence their data — the exact misreading this file is for.
    """
    envelopes = [envelope("ceterms:License"), envelope("ceterms:name"),
                 envelope("ceterms:copyrightHolder")]
    counted = rl.carrying_a_rights_field(envelopes)
    assert counted == {"envelopes": 3, "carrying_a_rights_field": 1,
                       "fields_looked_for": ["ceterms:copyrightHolder"],
                       "read_or_measured": "measured"}


def test_the_wrapper_is_not_searched_only_the_decoded_resource():
    """The envelope wrapper is registry bookkeeping.

    A key placed there must not count, or the measurement answers a question
    about the Registry's plumbing rather than about what publishers said.
    """
    assert rl.carrying_a_rights_field(
        [{"ceterms:copyrightHolder": "x", "decoded_resource": {"@graph": [{}]}}]
    )["carrying_a_rights_field"] == 0


def _quotes(page: str) -> list[str]:
    return [re.sub(r"[^a-z0-9 ]+", " ",
                   re.sub(r"\s+", " ", block.replace("> ", " ")).lower()).strip()
            for block in re.findall(r"(?m)((?:^> .*\n)+)", page)]


def test_every_quoted_term_on_the_page_is_in_the_record(record):
    flat = re.sub(r"\s+", " ", re.sub(
        r"[^a-z0-9 ]+", " ", json.dumps(record, ensure_ascii=False).lower()))
    page = PAGE.read_text()
    unmatched = [q for q in _quotes(page)
                 if re.sub(r"\s+", " ", q) not in flat]
    # The CC BY 4.0 sentence is quoted from credreg.net's FOOTER to show where
    # the confusion starts. It is not part of the terms this module reads, so
    # it is the one blockquote that is not in the record.
    assert len(unmatched) == 1 and "creative commons" in unmatched[0]


def test_every_recorded_sentence_is_quoted_on_the_page(record):
    page = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", PAGE.read_text().lower()))
    for field in ("grant", "restriction", "developer_agreement"):
        value = record["terms_of_use"][field]
        words = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", value.lower())).strip()
        assert words in page, f"{field} is recorded but not quoted on the page"


def test_the_page_states_the_count_and_the_date_the_record_holds(record):
    page = PAGE.read_text()
    counted = record["records"]
    assert (f"{counted['carrying_a_rights_field']} of {counted['envelopes']}"
            in page), "the page no longer states the measured count"
    read_on = re.search(r"Read on \*\*(\d{4}-\d{2}-\d{2})\*\*", page)
    assert read_on and read_on.group(1) == record["retrieved_at"]


def test_the_page_does_not_call_the_registry_data_cleared():
    """The whole point of #56.

    Asserted on the words a reader acts on, because the failure mode is a
    document that reads as permission.
    """
    page = PAGE.read_text().lower()
    assert "not cleared. do not load." in page
    assert "cc by 4.0 (#28)" in page
    # The operative sentence, not just the table. Dropping the "not" from it
    # left every other assertion here green while the document told a reader
    # the opposite of what it was written to say.
    assert ("loading registry records into a published graph is not permitted"
            in page)
    assert "#58 should not proceed on the assumption that it may" in page
