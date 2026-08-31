"""The licence readers, and the page they produced.

No test here fetches anything. Every reader in `etl.licence_positions` takes
page TEXT rather than a URL, so these hand it fixtures directly instead of
monkeypatching a fetch — the seam exists precisely so the indirection does not
have to be rebuilt here.

The page is checked against `docs/sources/licences-measured.json`, written by
`python -m etl.probe_licences --record`. That is the SCED arrangement: a
committed record makes the doc checkable offline, and the live pages are
re-read when a person decides to run the probe.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import licence_positions as lp
from etl import probe_licences

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "licences.md"
RECORD = ROOT / "docs" / "sources" / "licences-measured.json"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text())


DATABASE_PAGE = """
<html><head><style>p { color: red }</style></head><body>
<script>var licence = "this is not the licence";</script>
<h1>O*NET&reg; 31.0 Database Content License</h1>
<p>Except as noted below, the content of the O*NET 31.0 Database is licensed
under a <a href="#">Creative Commons Attribution 4.0 International License</a>.</p>
<p>This page includes information from the O*NET 31.0 Database by the U.S.
Department of Labor, Employment and Training Administration (USDOL/ETA). Used
under the CC BY 4.0 license. O*NET&reg; is a trademark of USDOL/ETA.</p>
<h2>License Exceptions</h2>
<p>This license applies only to downloadable files on the following pages:</p>
<ul><li>O*NET Database</li><li>Database Releases Archive</li>
<li>Spanish Language Resources</li></ul>
<p>To copy or adapt information from the O*NET Career Exploration Tools, see
the Career Exploration Tools License page.</p>
<p>&lt;keep-this-text&gt;</p>
</body></html>
"""

CROSSWALKS_PAGE = """
<html><body>
<h1>Education (CIP), DOT, Apprenticeship (RAPIDS)</h1>
<a href="a.xlsx">Classfication of Instructional Programs (CIP) (XLSX)</a>
<a href="b.xlsx">Registered Apprenticeship Partners Information Data System
(RAPIDS) (XLSX)</a>
<footer>Crosswalk Files by U.S. Department of Labor, Employment and Training
Administration is licensed under a Creative Commons Attribution 4.0
International License.</footer>
</body></html>
"""

URBAN_PAGE = """
<html><body><h2>Data Policy and Terms of Use</h2>
<p>All data made available via the Education Data Portal in any form is
licensed to you under the <a href="#">Open Data Commons Attribution License
(ODC-By) v1.0</a>.</p>
<h3>Citing these data</h3>
<p>[dataset names], Education Data Portal (Version ), Urban Institute,
accessed Month, DD, YYYY, https://educationdata.urban.org/documentation/,
made available under the ODC Attribution License.</p>
</body></html>
"""


def test_script_and_style_are_removed_before_the_tags_are():
    """The bug that made the first version refuse a page it had loaded.

    Strip tags first and the page's inline JavaScript survives as prose. On
    the real O*NET page that is most of what is left, and the word "licence"
    appears inside it — so the failure is not an empty result, it is a
    plausible wrong one.
    """
    flat = lp.flatten(DATABASE_PAGE)
    assert "this is not the licence" not in flat
    assert "color: red" not in flat


def test_entities_are_decoded_after_the_tags_and_not_before():
    """`O*NET&reg;` has to become `O*NET®` or the version is unreachable.

    Both halves are needed and the second is the one that pins the ORDER.
    Decoding first also produces `O*NET®`, so the first two assertions pass
    either way — they were the whole test, and swapping the order survived
    them. `&lt;keep-this-text&gt;` decodes to something the tag-stripper eats,
    so it is present only when the entities are decoded last.
    """
    flat = lp.flatten(DATABASE_PAGE)
    assert "O*NET® 31.0" in flat
    assert "&reg;" not in flat
    assert "keep-this-text" in flat


def test_the_database_licence_is_read_with_its_exception_list():
    read = lp.onet_database(DATABASE_PAGE)
    assert read["version"] == "31.0"
    assert read["licence"].startswith("Except as noted below")
    assert read["attribution"].endswith("trademark of USDOL/ETA.")
    assert "Spanish Language Resources" in read["applies_only_to"]


def test_the_exception_list_does_not_name_the_crosswalks_page():
    """The finding the whole document rests on.

    Asserted on the extracted list rather than on prose in the doc, so it
    fails if O*NET ever adds the crosswalks page and the page's argument
    stops being true.
    """
    applies_to = lp.onet_database(DATABASE_PAGE)["applies_only_to"]
    assert "rosswalk" not in applies_to


def test_the_crosswalk_files_carry_their_own_notice():
    read = lp.onet_crosswalks(CROSSWALKS_PAGE)
    assert read["licence"].startswith("Crosswalk Files by U.S. Department of Labor")
    assert len(read["files_this_repo_reads"]) == 2


def test_a_crosswalks_page_naming_neither_workbook_is_refused():
    """An empty list read as an ordinary result while saying the opposite.

    The notice on that page is what clears the two workbooks this repo reads.
    A page carrying the notice and naming neither file does not clear them —
    but `files_this_repo_reads: []` alongside a perfectly good licence string
    looks like a page that simply lists nothing, and the caller records it as
    cleared.
    """
    moved = CROSSWALKS_PAGE.replace("Classfication", "Renamed").replace(
        "Registered Apprenticeship Partners", "Renamed Apprenticeship")
    assert moved != CROSSWALKS_PAGE
    with pytest.raises(lp.MalformedSource, match="named neither workbook"):
        lp.onet_crosswalks(moved)


def test_one_workbook_renamed_is_recorded_not_refused():
    """A publisher retiring one file is ordinary; retiring both is not.

    Refusing on either would make an unremarkable rename look like a licence
    failure, which is the direction that gets a guard switched off.
    """
    one_gone = CROSSWALKS_PAGE.replace("Classfication", "Renamed")
    assert one_gone != CROSSWALKS_PAGE
    read = lp.onet_crosswalks(one_gone)
    assert read["files_this_repo_reads"] == [
        "Registered Apprenticeship Partners Information Data System (RAPIDS)"]
    assert read["licence"].startswith("Crosswalk Files")


def test_the_urban_portal_licence_and_citation_are_read():
    read = lp.urban_portal(URBAN_PAGE)
    assert "(ODC-By) v1.0" in read["licence"]
    assert read["citation"].startswith("[dataset names]")


@pytest.mark.parametrize("reader,page,missing,names", [
    (lp.onet_database, DATABASE_PAGE, "Creative Commons Attribution 4.0",
     "the Creative Commons licence sentence"),
    (lp.onet_crosswalks, CROSSWALKS_PAGE, "Crosswalk Files by",
     "the crosswalk files licence notice"),
    (lp.urban_portal, URBAN_PAGE, "Open Data Commons",
     "the Open Data Commons licence sentence"),
])
def test_a_page_without_its_licence_sentence_is_refused(reader, page, missing, names):
    """A cookie wall answers 200. Every field then comes back blank.

    `match=` names the SPECIFIC guard. Matching on "Refusing rather than" —
    the boilerplate every `_one` call shares — is exactly the failure this
    test's own docstring warned about: it passes when a different guard fires,
    so a reader whose own guard had been deleted stayed green as long as
    something else refused first.

    The removal is asserted too. A `replace` that matches nothing presents an
    intact page to a refusal test.
    """
    damaged = page.replace(missing, "REMOVED")
    assert damaged != page, f"{missing!r} is not in the fixture as written"
    with pytest.raises(lp.MalformedSource, match=re.escape(names)):
        reader(damaged)


def test_the_record_and_the_page_quote_the_same_licences(record):
    """Both directions.

    One direction alone lets an invented quote sit on the page unchallenged,
    which is the defect the SCED page had.
    """
    page = PAGE.read_text()
    quoted = {re.sub(r"\s+", " ", block.replace("> ", " ")).strip()
              for block in re.findall(r"(?m)((?:^> .*\n)+)", page)}
    for section in ("onet_database", "onet_crosswalks", "urban_portal"):
        for field in ("licence", "attribution", "citation", "applies_only_to"):
            value = record[section].get(field)
            if value is None:
                continue
            # The page renders the exception list with em-dashes between the
            # three page names; compare on the words, not the separators.
            words = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
            words = re.sub(r"\s+", " ", words).strip()
            assert any(words in re.sub(r"\s+", " ",
                                       re.sub(r"[^a-z0-9 ]+", " ", q.lower())).strip()
                       for q in quoted), f"{section}.{field} is not quoted on the page"


def test_every_blockquote_on_the_page_comes_from_the_record(record):
    """The other direction — nothing quoted that was never read."""
    # `ensure_ascii=False`, or `O*NET®` is escaped to `\u00ae` in the dump and
    # normalises to the word "u00ae" — which is not on the page, so the record
    # would appear not to contain a quote it does contain.
    flat = re.sub(r"[^a-z0-9 ]+", " ",
                  json.dumps(record, ensure_ascii=False).lower())
    flat = re.sub(r"\s+", " ", flat)
    page = PAGE.read_text()
    for block in re.findall(r"(?m)((?:^> .*\n)+)", page):
        quote = re.sub(r"\s+", " ", block.replace("> ", " ")).strip()
        words = re.sub(r"\s+", " ",
                       re.sub(r"[^a-z0-9 ]+", " ", quote.lower())).strip()
        assert words in flat, f"quoted on the page but not in the record: {quote[:70]}"


def test_the_record_names_the_date_it_was_read(record):
    """`#46` forbids a `cleared` row without the date it was checked.

    SCOPED to the sentence that makes the claim. `in PAGE.read_text()` was
    satisfied by any of the three places the date appears, so changing the one
    the reader believes — "read on **date**" — left the test green.
    """
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["retrieved_at"])
    claimed = re.search(r"read on\s+\*\*(\d{4}-\d{2}-\d{2})\*\*", PAGE.read_text())
    assert claimed, "the page no longer says when it was read"
    assert claimed.group(1) == record["retrieved_at"]


def test_the_probe_prints_the_exception_finding(capsys, monkeypatch):
    """The print block runs in no other test, so both mutants survived it."""
    pages = {lp.ONET_DATABASE: DATABASE_PAGE,
             lp.ONET_CROSSWALKS: CROSSWALKS_PAGE,
             lp.URBAN_PORTAL: URBAN_PAGE}
    monkeypatch.setattr(probe_licences, "page_text", lambda url: pages[url])
    probe_licences.probe()
    printed = capsys.readouterr().out
    assert "the crosswalks page is NOT on that list" in printed
    assert "(ODC-By) v1.0" in printed


def bare_trademark(text: str) -> list[str]:
    """Lines carrying an unescaped `O*NET` that markdown will render as emphasis.

    Code spans, fenced blocks and indented blocks are excluded: an asterisk
    inside them is literal, and `code-sets.md` quotes a console listing that
    must keep its bare form.
    """
    found = []
    fence = False
    for line in text.splitlines():
        # `lstrip("> ")` as well as whitespace: a fence inside a blockquote
        # opens with `> ```, and the plain `lstrip()` never saw it — so an
        # example quoted inside a blockquote was scanned as prose and its
        # bare asterisks reported.
        opener = line.lstrip().lstrip("> ").lstrip()
        if opener.startswith("```") or opener.startswith("~~~"):
            fence = not fence
            continue
        if fence or line.startswith("    ") or line.startswith("\t"):
            continue
        # DOUBLE backticks first, and they are the wider span. ``a `b` c`` is
        # one code span containing a backtick, and matching the single form
        # first splits it into two, leaving the middle exposed as prose.
        spans = [(m.start(), m.end()) for m in re.finditer(r"``.+?``", line)]
        for m in re.finditer(r"`[^`]*`", line):
            if not any(a <= m.start() < b for a, b in spans):
                spans.append((m.start(), m.end()))
        for m in re.finditer(r"O(?!\\)\*NET", line):
            if not any(a <= m.start() < b for a, b in spans):
                found.append(line.strip())
    return found


def test_the_attribution_quote_reproduces_the_trademark():
    """The one string this page argues hardest must be reproduced exactly.

    Markdown pairs bare asterisks into emphasis within a block. The
    attribution blockquote carries two, so unescaped it renders as italics
    with both asterisks eaten — "ONET 31.0 Database ... ONET is a trademark" —
    which is the one form O*NET's own terms do not permit.

    The two quote tests either side of this one cannot see it: both normalise
    through `[^a-z0-9 ]+`, which deletes the asterisk on both sides, so they
    pass identically whether the trademark survives rendering or not.
    """
    page = PAGE.read_text()
    # The blockquote is its own contiguous run of `>` lines. Bounding it on a
    # trailing blank line meant the quote ending the file, or followed
    # directly by a heading, matched nothing — and the assertion below then
    # failed for a reason that has nothing to do with the trademark.
    lines = page.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.startswith("> This page includes information")), None)
    assert start is not None, "the attribution blockquote is no longer on the page"
    end = start
    while end + 1 < len(lines) and lines[end + 1].startswith(">"):
        end += 1
    attribution = "\n".join(lines[start:end + 1])
    assert attribution.count(r"O\*NET") == 2, \
        "the attribution quote must escape both trademarks, or they italicise"


def test_no_document_renders_the_trademark_as_emphasis():
    """A repo-wide ratchet, because this regresses on the next edit anywhere.

    **Deliberately wider than this PR.** The failure is invisible in the
    source and only shows in the rendered page, so a check scoped to the file
    that happened to introduce it would let the next document reintroduce it
    silently. The cost is that an unrelated branch can fail this test; the
    message names the file and the line, so the fix is one escape.
    """
    scanned = {}
    for doc in sorted((ROOT / "docs").rglob("*.md")):
        scanned[doc] = bare_trademark(doc.read_text())
    offenders = {str(d.relative_to(ROOT)): lines
                 for d, lines in scanned.items() if lines}
    assert not offenders, f"unescaped O*NET will italicise: {offenders}"

    # Not vacuous: the corpus really does discuss the trademark. Without this,
    # a rename of the docs tree would pass the assertion above by scanning
    # nothing at all.
    #
    # Asserted on the DOCUMENT that must contain them, not on a repo-wide
    # count. `escaped >= 40` was a number nobody could derive — it drifts with
    # every unrelated edit, and it says nothing about whether the one page
    # this PR is about was scanned.
    licences = ROOT / "docs" / "sources" / "licences.md"
    assert licences in scanned, "the licence page was not scanned at all"
    assert scanned[licences] == [], "the licence page has a bare trademark"
    assert licences.read_text().count(r"O\*NET") >= 5, \
        "the licence page no longer discusses the trademark — did it move?"
