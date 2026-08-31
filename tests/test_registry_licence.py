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
    page = PAGE.read_text()
    counted = record["records"]
    assert (f"{counted['carrying_copyright_holder']} of {counted['envelopes']}"
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


# --------------------------------------------------------------------------
# the borrowed fetching layer, and everything that is "not the document asked
# for". `probe` imports `etl.registry_read` lazily, so these patch the module
# it will import rather than a name bound at import time.
# --------------------------------------------------------------------------

def drive_probe(monkeypatch, *, get=None, parse=None, page_text=None,
                total=None):
    """Every door `probe` can reach the network through, closed.

    `total` was missing, and it is not optional: `probe` calls it once per
    resource type to size the sample, so four live HEAD requests to the
    Credential Registry went out on every run of this file — under a docstring
    saying nothing here fetches. Measured: four socket connections.

    The default population is a real one (the course search returned 47,862),
    so `sample_pages` spreads over a realistic number of pages rather than
    collapsing to a single one and hiding a stride bug.
    """
    from etl import registry_read
    monkeypatch.setattr(rl, "page_text",
                        page_text or (lambda url, timeout=60: TERMS_PAGE))
    monkeypatch.setattr(rl, "graph_of", lambda payload, what: VOCABULARY_GRAPH)
    monkeypatch.setattr(registry_read, "total", total or (lambda path: 47_862))
    monkeypatch.setattr(registry_read, "get", get or (lambda url: b"[]"))
    monkeypatch.setattr(registry_read, "parse", parse or (lambda body, what: []))


VOCABULARY_GRAPH = [{"@id": "ceterms:copyrightHolder"}]


def test_a_registry_outage_is_refused_rather_than_a_traceback(monkeypatch):
    """`registry_read` raises its OWN classes, and one shares this module's name.

    `main` catches `registry_licence.MalformedSource`. `registry_read.get`
    raises `HttpStatus`, and its `parse` raises a DIFFERENT class also called
    `MalformedSource`, so a 503 from the Registry produced a traceback and no
    exit code — while `page_text`, three lines up, converts exactly this into
    a refusal for the pages it fetches itself.
    """
    from etl.registry_read import HttpStatus

    def boom(url):
        raise HttpStatus(503, url)

    drive_probe(monkeypatch, get=boom)
    with pytest.raises(rl.MalformedSource, match="search"):
        rl.probe(quiet=True)
    assert rl.main(["--json"]) == 3


def test_a_search_page_that_is_not_json_is_refused(monkeypatch):
    from etl.registry_read import MalformedSource as ReadRefused

    def bad(body, what):
        raise ReadRefused(f"{what} did not parse as JSON")

    drive_probe(monkeypatch, parse=bad)
    with pytest.raises(rl.MalformedSource, match="did not parse as JSON"):
        rl.probe(quiet=True)


def test_a_search_page_that_is_an_object_is_refused_not_counted(monkeypatch):
    """An error body that is a JSON object extended `envelopes` with its KEYS.

    `carrying_a_rights_field` then called `.get` on a `str`. `probe_registry`
    already guards this because the Registry has returned other shapes; this
    module diverged from it.
    """
    drive_probe(monkeypatch,
                parse=lambda body, what: {"error": "rate limited"})
    with pytest.raises(rl.MalformedSource, match="not a list of envelopes"):
        rl.probe(quiet=True)


@pytest.mark.parametrize("payload,expected", [
    ("<html>502 Bad Gateway</html>", "did not parse as JSON"),
    ('["not", "an", "object"]', "no @graph list"),
    ('{"nope": 1}', "no @graph list"),
    ('{"@graph": {"a": 1}}', "no @graph list"),
])
def test_a_vocabulary_that_is_not_the_vocabulary_is_refused(payload, expected):
    """`json.loads(...)["@graph"]` fails three ways, none of them catchable."""
    with pytest.raises(rl.MalformedSource, match=expected):
        rl.graph_of(payload, "the CTDL vocabulary")


@pytest.mark.parametrize("envelope", [
    {"decoded_resource": None},
    {"decoded_resource": "a string"},
    {"decoded_resource": {"@graph": None}},
    {"decoded_resource": {"@graph": {"ceterms:copyrightHolder": "x"}}},
    {"decoded_resource": {"@graph": ["ceterms:copyrightHolder"]}},
])
def test_a_misshapen_envelope_counts_as_saying_nothing(envelope):
    """The count must not crash, and must not report a field that is not there.

    A non-list `@graph` iterates its KEYS, so `field in node` became a
    substring test against a string — which would have reported a rights field
    on a record that carries none, on the page whose whole finding is that
    zero records carry one.
    """
    got = rl.carrying_a_rights_field([envelope])
    assert got == {"envelopes": 1, "carrying_copyright_holder": 0,
                   "fields_looked_for": list(rl.RIGHTS_FIELDS),
                   "read_or_measured": "measured"}


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


def test_probe_spreads_the_pages_it_asks_for(monkeypatch):
    """The mutation the record-based tests could not see.

    Those tests read `registry-licence-measured.json`, which is committed — so
    reverting `probe` to `range(1, 4)` left them green while the next
    `--record` would have written a head sample. The pages actually requested
    have to be checked against the code, not against a file the code wrote
    last time.
    """
    from etl import registry_read
    from etl import registry_licence as rl

    asked: list[str] = []

    def fake_get(url):
        asked.append(url)
        return b"[]"

    monkeypatch.setattr(registry_read, "total", lambda path: 47_862)
    monkeypatch.setattr(registry_read, "get", fake_get)
    monkeypatch.setattr(registry_read, "parse",
                        lambda body, what: [{"decoded_resource": {"@graph": [{}]}}])
    monkeypatch.setattr(rl, "page_text", lambda url, timeout=60: (
        TERMS_PAGE if url == rl.TERMS_URL else json.dumps({"@graph": VOCABULARY})))

    rl.probe(quiet=True)

    pages = [int(re.search(r"[?&]page=(\d+)", u).group(1)) for u in asked]
    assert pages, "probe asked for nothing"
    # Not 1, 2, 3. With a population this size the stride is large, so the
    # highest page read must be far past the head.
    assert max(pages) > 100, f"pages were taken off the head: {sorted(set(pages))}"
    assert len(set(pages)) > 1, "only one page was read, so nothing is spread"


def test_probe_records_how_it_sampled(monkeypatch):
    """`sampling` must reach the result, or the record has nothing to state.

    Emptying it left every record-based assertion green, because those read
    the committed file rather than a fresh run.
    """
    from etl import registry_read
    from etl import registry_licence as rl

    monkeypatch.setattr(registry_read, "total", lambda path: 47_862)
    monkeypatch.setattr(registry_read, "get", lambda url: b"[]")
    monkeypatch.setattr(registry_read, "parse",
                        lambda body, what: [{"decoded_resource": {"@graph": [{}]}}])
    monkeypatch.setattr(rl, "page_text", lambda url, timeout=60: (
        TERMS_PAGE if url == rl.TERMS_URL else json.dumps({"@graph": VOCABULARY})))

    sampling = rl.probe(quiet=True)["records"]["sampling"]
    assert set(sampling) == {"course", "credential",
                             "learning_opportunity_profile", "pathway"}
    for kind, how in sampling.items():
        assert "stride" in how, f"{kind} was not described as spread: {how}"


def test_this_file_opens_no_sockets():
    """The docstring says nothing here fetches. It was not true.

    `drive_probe` patched `page_text`, `graph_of`, `get` and `parse` but not
    `total` — which `probe` calls once per resource type to size the sample —
    so four live HEAD requests went to the Credential Registry on every run of
    this file, and it took six seconds. It takes 0.08 now.

    Asserted rather than trusted: a missing patch is invisible until someone
    watches the socket, and the next helper added here can reintroduce it.
    """
    import subprocess
    import sys

    watcher = (
        "import socket\n"
        "hits = []\n"
        "class Watch(socket.socket):\n"
        "    def connect(self, addr):\n"
        "        hits.append(addr)\n"
        "        return super().connect(addr)\n"
        "socket.socket = Watch\n"
        "import pytest\n"
        "code = pytest.main(['-q', '--no-header', '-p', 'no:cacheprovider',\n"
        "                    'tests/test_registry_licence.py',\n"
        "                    '--deselect',\n"
        "                    'tests/test_registry_licence.py::"
        "test_this_file_opens_no_sockets'])\n"
        "print('CONNECTS', len(hits))\n"
    )
    result = subprocess.run([sys.executable, "-c", watcher],
                            capture_output=True, text=True,
                            cwd=str(ROOT), timeout=120)
    reported = [line for line in result.stdout.splitlines()
                if line.startswith("CONNECTS")]
    assert reported, f"the watcher did not report:\n{result.stdout[-600:]}"
    assert reported[-1] == "CONNECTS 0", (
        f"{reported[-1]} — a test in this file reached the network. Something "
        f"`probe` calls is unpatched; `total` was the one that hid here.")
