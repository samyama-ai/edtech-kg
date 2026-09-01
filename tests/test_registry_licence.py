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
from tests.spelling import position, spelled

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
    assert counted == {"envelopes": 3, "carrying_copyright_holder": 1,
                       "fields_looked_for": ["ceterms:copyrightHolder"],
                       "read_or_measured": "measured"}


def test_the_wrapper_is_not_searched_only_the_decoded_resource():
    """The envelope wrapper is registry bookkeeping.

    A key placed there must not count, or the measurement answers a question
    about the Registry's plumbing rather than about what publishers said.
    """
    assert rl.carrying_a_rights_field(
        [{"ceterms:copyrightHolder": "x", "decoded_resource": {"@graph": [{}]}}]
    )["carrying_copyright_holder"] == 0


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
    page = PAGE.read_text(encoding="utf-8")
    counted = record["records"]
    assert (f"{counted['carrying_copyright_holder']} of {counted['envelopes']}"
            in page), "the page no longer states the measured count"
    read_on = re.search(r"Read on \*\*(\d{4}-\d{2}-\d{2})\*\*", page)
    assert read_on and read_on.group(1) == record["retrieved_at"]

    # The rights-term count, which was typed on the page and in a docstring and
    # pinned in neither. The docstring said four while everything else said
    # five; removing the number from the docstring did not close the gap, it
    # moved it one file over. The page states it AND tabulates them, so both
    # are checked against the record rather than against each other.
    returns = re.search(r"returns \*\*(\w+)\*\*", page)
    assert returns, "the page no longer states how many rights-shaped terms"
    terms = record["rights_terms_in_ctdl"]
    assert spelled(returns.group(1)) == len(terms), (
        f"the page says the search returns {returns.group(1)}; the record "
        f"holds {len(terms)}: {terms}")
    for term in terms:
        assert f"`{term}`" in page, (
            f"{term} is in the record and not in the page's table, so a "
            f"reader counting the rows gets a different answer")


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


def test_the_page_quotes_no_split_the_record_does_not_hold(record):
    """"75 each" was the PLAN — 25 per page times three pages, times four types.

    The record holds one flat total. If any type returned short the JSON would
    stay self-consistent, every count test would still pass, and the page's
    per-type breakdown would be quietly false.
    """
    page = PAGE.read_text()
    # Both spellings. The page writes thousands with commas and the record
    # holds an int, so `str(398)` matched today and `str(1234)` would not have
    # — a check that works only while the number stays small.
    envelopes = record["records"]["envelopes"]
    assert (str(envelopes) in page or f"{envelopes:,}" in page), (
        f"the page does not state the {envelopes} records the record holds")
    assert "75 each" not in page
    per_kind = re.search(r"(\d+) each of", page)
    assert not per_kind, f"the page quotes a per-type split the record lacks: {per_kind}"


def test_the_record_states_how_each_type_was_sampled(record):
    """The blocking finding of the second review, pinned.

    The first version read pages 1, 2 and 3 of each search consecutively —
    which is not a sample of the Registry, it is a sample of whatever sorts
    first. `registry_read.sample_pages` exists to prevent exactly that, and
    `describe` reports what the walk reached. Both are now used, and the
    description is carried into the record so a reader can see the shape of
    the sample rather than take it on trust.
    """
    sampling = record["records"]["sampling"]
    assert set(sampling) == {"course", "credential",
                             "learning_opportunity_profile", "pathway"}
    for kind, how in sampling.items():
        assert how, f"{kind} has no sampling description"
        # Either the pages were spread, or the whole population was read.
        # "biased toward whatever sorts first" is `describe`'s own wording for
        # the head sample, and it must not appear.
        assert ("stride" in how or "whole population" in how), \
            f"{kind} was not spread and is not exhaustive: {how}"
        assert "biased toward whatever sorts first" not in how, \
            f"{kind} is a head sample: {how}"


def test_the_page_repeats_the_sampling_the_record_holds(record):
    """A reader cannot check a sample whose shape is not on the page.

    The record alone is not enough — the document is what anyone reads, and
    the review's point was that neither said pages 1-3 had been taken off the
    head. The stride figures are quoted, so the page cannot drift back to
    claiming a spread it did not have.
    """
    page = re.sub(r"\s+", " ", PAGE.read_text())
    for kind, how in record["records"]["sampling"].items():
        if "stride" not in how:
            continue
        stride = re.search(r"stride of ([\d,]+)", how).group(1)
        # The page writes thousands with a comma; the description may not.
        variants = {stride, f"{int(stride.replace(',', '')):,}"}
        assert any(f"stride of {v}" in page for v in variants), \
            f"the page does not state {kind}'s stride ({stride})"


def test_the_record_carries_the_verdict_not_only_the_evidence(record):
    """The committed record states the conclusion, not only the evidence."""
    verdict = record.get("verdict", "")
    assert verdict, "the record states no verdict"
    assert "not cleared" in verdict.lower()
    assert "developer agreement" in verdict.lower(), (
        "the verdict does not say what would change the answer")


#: A row is unresolved if its licence cell says so, in any of the ways this
#: table has said it. The list is the weak point and it has already cost one
#: miscount: O\\*NET's "terms to confirm" matched none of the first three, so
#: the counter read three, agreed with prose that said three, and both were
#: wrong by the same row. A fourth phrasing would do it again — which is why
#: the test below does not stop at counting.
#: "terms to confirm", not "to confirm". The looser form inverts: a cleared
#: cell reading "Cleared — public domain, no need to confirm" would be counted
#: as unresolved, so the check fires on somebody at the moment they CLEAR a
#: row, which reads as "you broke the document".
UNRESOLVED = ("not cleared", "not settled", "not yet checked", "terms to confirm")


def _scope_rows() -> list[tuple[str, str, str]]:
    scope = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    rows = re.findall(r"(?m)^\| (?!Source\b)(?!-)([^|]+)\|([^|]*)\|([^|]*)\|$", scope)
    assert rows, "the scope licence table could not be read"
    return rows


def test_scope_counts_the_uncleared_rows_it_actually_lists():
    """The paragraph said two while the table held three.

    It is prose about a table three lines above it, so it drifts every time a
    row is added — which is exactly what happened when this PR added the
    Registry row. Counted from the table rather than trusted.
    """
    rows = _scope_rows()
    scope = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    uncleared = [r for r in rows
                 if any(p in r[2].lower() for p in UNRESOLVED)]
    claimed = re.search(r"\*\*(\w+) of those are not cleared\*\*", scope)
    assert claimed, "scope.md no longer states how many rows are not cleared"
    # `spelled`, not a five-entry dict. The table has eight rows, so six
    # through eight are reachable and the dict raised a bare `KeyError` there
    # — a traceback from a test whose whole subject is legibility.
    assert spelled(claimed.group(1)) == len(uncleared), (
        f"scope.md claims {claimed.group(1)} uncleared rows; the table has "
        f"{len(uncleared)}: {[r[0].strip() for r in uncleared]}")

    # The SECOND spelled number about the same table, three lines below the
    # first. It said "two of these … and the third" while the count above it
    # said four — the same miscount, in the sentence a reader acts on when
    # sizing the backlog, and nothing read it.
    split = re.search(r"(\w+) of these could clear.*?the (\w+) cannot clear",
                      scope, re.S)
    assert split, "scope.md no longer splits the uncleared rows into can and cannot"
    assert spelled(split.group(1)) + 1 == len(uncleared), (
        f"scope.md says {split.group(1)} rows could clear on a reading plus "
        f"one that cannot, against {len(uncleared)} uncleared rows")
    assert position(split.group(2)) == len(uncleared), (
        f"scope.md calls the row needing a signature the {split.group(2)} of "
        f"{len(uncleared)}")


def test_every_uncleared_row_is_named_in_the_paragraph_that_counts_them():
    """Counting right is not the same as accounting for them.

    The count and the prose agreed at three while the table held four,
    because the row they both missed was the mildest one — O\\*NET, "terms to
    confirm". It was absent from the count AND unnamed in every bullet under
    it, so nothing in the document pointed at the gap. A number can be made
    to agree with a list by leaving the same row out of both.

    This asks the other question: is each row the table marks unresolved
    actually spoken about? That does not depend on how the licence cell is
    worded, so it survives a fifth phrasing the counter would miss.
    """
    scope = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    # THE BULLET RUN, not everything up to the next heading. The span was
    # ~1,100 characters running past the bullets through two more paragraphs,
    # so any incidental word in the trailing prose satisfied a row: deleting
    # the O\\*NET bullet passed if "network" appeared anywhere in it, and
    # deleting the Credential Registry bullet passed on a stray mention of
    # "Credential Engine". Both are ordinary edits. `main` has since added
    # another paragraph inside the old span, which is more prose for a missing
    # bullet to hide behind.
    after = scope[scope.index("of those are not cleared"):]
    bullets = []
    for line in after.splitlines()[1:]:
        if line.startswith("- "):
            bullets.append(line)
        elif bullets and not line.startswith(" "):
            break
        elif bullets:
            bullets.append(line)
    paragraph = "\n".join(bullets)
    assert paragraph.strip(), "no bullet list follows the uncleared count"

    missing = []
    for name, _publisher, licence in _scope_rows():
        if not any(p in licence.lower() for p in UNRESOLVED):
            continue
        # The longest word in the source name — "Credential", "Institute",
        # "catalogue", "NET". The gaps this had were both in the SPAN, not
        # here: a stray "network" or "Credential Engine" in the trailing prose
        # covered a deleted bullet. With the span cut to the bullets those
        # sentences are outside it, and a bullet is only ever about its own
        # row. Requiring every word instead would fail honestly-worded prose —
        # the Urban row carries "Education", which no bullet says.
        #
        # Strict on renaming either side. That is the trade; the failure names
        # the row, so the fix is obvious.
        words = [w for w in re.findall(r"[A-Za-z]+", name) if len(w) > 2]
        assert words, f"the row name {name!r} has no word to look for"
        if max(words, key=len) not in paragraph:
            missing.append(name.strip())
    assert not missing, (
        f"the table marks these rows unresolved and the paragraph counting "
        f"them never names them: {missing}")


def test_every_date_for_this_source_agrees_with_the_record(record):
    """Three places state when the terms were read, and they drifted.

    `docs/scope.md`'s row said 2026-08-28 while the page and the record said
    2026-08-31 — the row was written in one round and the measurement redone
    in another. A reader takes whichever they meet first.
    """
    import re as _re

    read_on = record["retrieved_at"]
    scope = (ROOT / "docs" / "scope.md").read_text(encoding="utf-8")
    row = [line for line in scope.splitlines()
           if line.startswith("| Credential Registry")]
    assert row, "the Credential Registry row is no longer in the scope table"
    dates = set(_re.findall(r"\d{4}-\d{2}-\d{2}", row[0]))
    assert dates == {read_on}, (
        f"the scope row states {sorted(dates)}; the record was read on "
        f"{read_on}")

    page = PAGE.read_text(encoding="utf-8")
    claimed = _re.search(r"Read on \*\*(\d{4}-\d{2}-\d{2})\*\*", page)
    assert claimed and claimed.group(1) == read_on


def test_the_record_is_written_in_the_characters_it_quotes():
    """Read as RAW text, not through `json.loads`.

    `json.loads` decodes `\\u2014` back to an em dash, so an assertion made
    through it passes whichever way the file was written and the escape
    survives every round. The sibling probes write the character; a record
    differing from them only in encoding is a diff nobody reads and a
    regeneration nobody expects.
    """
    raw = RECORD.read_text(encoding="utf-8")
    assert "\\u" not in raw, (
        "the record carries escaped characters, so it was written with "
        "ensure_ascii on and does not match what `--record` now produces")


def test_the_committed_note_is_the_one_the_writer_would_write():
    """Two copies otherwise — the file's and the writer's — and the drift only
    shows up as a surprise diff on the next refresh."""
    committed = json.loads(RECORD.read_text(encoding="utf-8"))
    assert committed["_"] == rl.RECORD_NOTE, (
        "the committed note and the note `--record` writes have drifted; "
        "the next refresh will rewrite it")

