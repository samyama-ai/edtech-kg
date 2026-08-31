"""The licence PAGE and the committed record — edtech-kg#13, #14.

Split from `tests/test_licence_positions.py` when it passed the 500-line
review limit. Split by SUBJECT: that file exercises the three readers and the
fetch boundary; this one checks what the page and the record say, and the
scanner that keeps the trademark rendering correctly.

Nothing here fetches. `page_text` is monkeypatched wherever the probe is
driven.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from etl import licence_positions as lp
from etl import probe_licences
from tests.test_licence_positions import (CROSSWALKS_PAGE, DATABASE_PAGE,
                                          URBAN_PAGE)

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "sources" / "licences.md"
RECORD = ROOT / "docs" / "sources" / "licences-measured.json"


@pytest.fixture(scope="module")
def record() -> dict:
    """Its own, rather than imported.

    Importing a fixture by name binds it as a module global that every test
    taking `record` as a parameter then shadows — which reads as an unused
    import and three redefinitions, and works only by accident.
    """
    return json.loads(RECORD.read_text(encoding="utf-8"))


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


def test_the_record_stores_the_trademark_sign_not_its_escape(record):
    """The record's whole subject is reproducing a string exactly.

    `json.dumps` escapes non-ASCII by default, so O*NET's own attribution
    wording — the one they publish for verbatim reuse — was stored as
    `O*NET\\u00ae`. `probe_sced` already passes `ensure_ascii=False`; this did
    not.
    """
    raw = RECORD.read_text(encoding="utf-8")
    assert "\\u00ae" not in raw, "the record escapes the registered sign"
    assert "®" in record["onet_database"]["attribution"]


def test_the_exception_line_is_derived_from_the_list_not_asserted(capsys, monkeypatch):
    """It was hardcoded, on the one claim this document turns on.

    The printed line said the crosswalks page is absent from the exception
    list whether or not it was. Adding the page to the fixture must change
    what is printed, or the line is decoration.
    """
    pages = {lp.ONET_DATABASE: DATABASE_PAGE,
             lp.ONET_CROSSWALKS: CROSSWALKS_PAGE,
             lp.URBAN_PORTAL: URBAN_PAGE}
    monkeypatch.setattr(probe_licences, "page_text", lambda url: pages[url])
    probe_licences.probe()
    printed = capsys.readouterr().out
    assert "the crosswalks page is NOT on that list" in printed
    # ON THE OUTPUT. The source scan below only reads lines whose `strip()`
    # starts with `print(`, and three calls here span several lines with the
    # placeholder on a continuation — so dropping an `f` from one of those
    # left the suite green while the probe printed the braces. A brace in the
    # output is the defect regardless of how the call is laid out.
    assert "{" not in printed, (
        f"a placeholder reached the output — an f prefix is missing:\n"
        f"{[line for line in printed.splitlines() if '{' in line]}")

    with_crosswalks = DATABASE_PAGE.replace(
        "<li>Spanish Language Resources</li>",
        "<li>Spanish Language Resources</li><li>Crosswalk Files</li>")
    assert with_crosswalks != DATABASE_PAGE
    pages[lp.ONET_DATABASE] = with_crosswalks
    probe_licences.probe()
    printed = capsys.readouterr().out
    assert "the crosswalks page IS on that list" in printed, (
        "the line is hardcoded — it says the page is absent from a list that "
        "names it")


def test_record_and_json_together_print_both(capsys, monkeypatch, tmp_path):
    """`--json --record` accepted both and silently produced only the file."""
    pages = {lp.ONET_DATABASE: DATABASE_PAGE,
             lp.ONET_CROSSWALKS: CROSSWALKS_PAGE,
             lp.URBAN_PORTAL: URBAN_PAGE}
    monkeypatch.setattr(probe_licences, "page_text", lambda url: pages[url])
    destination = tmp_path / "out.json"
    monkeypatch.setattr(probe_licences, "RECORD", destination)
    assert probe_licences.main(["--json", "--record"]) == 0
    printed = capsys.readouterr().out
    # The path it actually wrote, not a directory spelled into the message.
    # This asserted the literal "docs/sources/out.json" — a record moved
    # anywhere else would have been reported at a path nothing was written to,
    # and the test said that was correct.
    assert f"wrote {destination}" in printed
    assert destination.exists()
    assert '"onet_database"' in printed, "--json produced nothing alongside --record"


# --------------------------------------------------------------------------
# the trademark scanner, against the shapes that fooled it
# --------------------------------------------------------------------------

def test_a_fence_opened_inside_a_blockquote_is_still_a_fence():
    """`> ``` ` never matched, so a quoted example was scanned as prose."""
    quoted = "> Example:\n>\n> ```\n> O*NET bare inside a quoted fence\n> ```\n"
    assert bare_trademark(quoted) == []


@pytest.mark.parametrize("line", [
    "Use ``O*NET `x` y`` here.",
    "Use ``a `b` O*NET`` here.",
    "``O*NET``",
])
def test_a_double_backtick_span_is_not_split_at_its_inner_backtick(line):
    """``a `b` c`` is ONE code span containing a backtick.

    Matching the single form first cut it in two, and the trademark landed in
    the gap between the halves — reported as prose from inside a code span.

    The fixtures are chosen to DIFFER between the two implementations. The
    first attempt used ``the `O*NET` field``, where the inner single-backtick
    span happens to cover the trademark on its own, so both versions passed
    and the mutation that removed double-backtick handling survived.
    """
    assert bare_trademark(line + "\n") == []


def test_genuine_prose_is_still_reported():
    """The false-negative direction. A scanner that finds nothing passes
    everything, which is how this guard would quietly stop working."""
    assert bare_trademark("O*NET is a trademark.\n") == ["O*NET is a trademark."]
    assert bare_trademark("O" + chr(92) + "*NET is a trademark.\n") == []


def test_the_probe_prints_the_address_it_read_not_the_variable_name():
    """A lint fix broke a different line, and the output shipped wrong.

    Removing an `f` prefix to silence F541 on one string took it off another,
    so the probe printed the literal `{ONET_CROSSWALKS}` to anyone who ran it.
    Nothing caught it: the print block was exercised, but only for the two
    lines the assertions named.
    """
    import re as _re

    source = (ROOT / "etl" / "probe_licences.py").read_text(encoding="utf-8")
    # Any print whose text contains a `{…}` placeholder must be an f-string.
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("print("):
            continue
        if "{" in stripped and not _re.search(r'print\(\s*f["\']', stripped):
            raise AssertionError(
                f"this print has a placeholder and is not an f-string, so it "
                f"will print the braces: {stripped[:90]}")


def test_a_refusal_exits_three_not_zero(monkeypatch, capsys):
    """A refusal reported as success is the failure the module argues against.

    `main` returning 0 on `MalformedSource` went unnoticed. If anything ever
    schedules this probe — and a weekly terms check is exactly what should —
    a silent zero is a licence change nobody hears about.
    """
    def refuse(url, timeout=60):
        raise lp.MalformedSource("the page did not answer")

    monkeypatch.setattr(probe_licences, "page_text", refuse)
    assert probe_licences.main([]) == 3
    assert "refused:" in capsys.readouterr().err


def test_the_record_writer_keeps_the_trademark_unescaped(monkeypatch, tmp_path):
    """Every other assertion targets the file already in git.

    Removing `ensure_ascii=False` from the writer went unnoticed, because the
    committed record is checked in and does not change when the code that
    writes it does.
    """
    pages = {lp.ONET_DATABASE: DATABASE_PAGE,
             lp.ONET_CROSSWALKS: CROSSWALKS_PAGE,
             lp.URBAN_PORTAL: URBAN_PAGE}
    monkeypatch.setattr(probe_licences, "page_text", lambda url: pages[url])
    written = tmp_path / "out.json"
    monkeypatch.setattr(probe_licences, "RECORD", written)
    assert probe_licences.main(["--record"]) == 0
    raw = written.read_text(encoding="utf-8")
    assert "®" in raw, "the writer escaped the registered sign"
    assert "\\u00ae" not in raw


def test_the_central_claim_is_asserted_against_the_record(record):
    """Not against a fixture written not to contain it.

    The document's whole argument is that the crosswalks page is absent from
    the Database licence's exception list. Asserting that on a hand-written
    fixture proves only that the fixture omits it. On the record, a refreshed
    measurement finding O*NET has added the page turns the suite red on the
    artifact the page actually cites.
    """
    assert record["onet_database"]["names_crosswalks_page"] is False, (
        "O*NET now names the crosswalks page in its exception list — the "
        "Database licence covers the workbooks this repo reads, and the page "
        "argues the opposite")
    assert "crosswalk" not in record["onet_database"]["applies_only_to"].lower()


def test_the_workbook_names_are_tied_to_the_record(record):
    """They were bullets in code spans, which neither round-trip direction sees.

    The page names the two workbooks this repo reads; if O*NET renames one,
    the record changes and the page does not.
    """
    page = PAGE.read_text(encoding="utf-8")
    named = record["onet_crosswalks"]["files_this_repo_reads"]
    assert named, "the record names no workbook"
    for workbook in named:
        assert workbook in page, (
            f"{workbook!r} is in the record and not on the page")


def test_the_modification_obligation_is_quoted_from_what_was_read(record):
    """The only ongoing compliance duty this document states.

    It was quoted on the page with nothing extracted behind it — inline
    italic inside a list item, so neither direction of the round-trip could
    see it, on a page whose own guarantee is that every quote is lifted
    rather than typed.
    """
    quoted = record["onet_database"]["modification"]
    assert "has modified all or some" in quoted
    # Blockquote markers stripped BEFORE whitespace is squashed. A markdown
    # quote wraps, so `> ` lands mid-sentence and a substring test fails for a
    # reason that has nothing to do with the words.
    page = re.sub(r"\s+", " ", re.sub(r"(?m)^> ", "", PAGE.read_text(encoding="utf-8")))
    assert re.sub(r"\s+", " ", quoted) in page, (
        "the modification wording on the page is not the one that was read")


def test_refreshing_the_record_does_not_delete_its_own_instructions(
        monkeypatch, tmp_path):
    """The record opens with a note naming the command that refreshes it, and
    that command did not write the key — so following the instruction removed
    it, and the next reader met a file with no explanation of where it came
    from or how to renew it.

    A record that documents itself has to be documented by the thing that
    writes it. Driven through `main`, because the defect was in the writer and
    not in what `probe` returns.
    """
    monkeypatch.setattr(probe_licences, "probe",
                        lambda quiet=False: {"retrieved_at": "2026-08-31"})
    destination = tmp_path / "licences-measured.json"
    monkeypatch.setattr(probe_licences, "RECORD", destination)
    assert probe_licences.main(["--record"]) == 0

    written = json.loads(destination.read_text(encoding="utf-8"))
    assert "_" in written, "the refresh dropped the record's own note"
    assert "--record" in written["_"]
    # First, so it is the first thing read rather than buried under the data.
    assert list(written)[0] == "_"


def test_the_committed_note_is_the_one_the_writer_would_write():
    """Two copies otherwise — the file's and the writer's — and the drift
    only shows up as a surprise diff on the next refresh."""
    committed = json.loads(RECORD.read_text(encoding="utf-8"))
    assert committed["_"] == probe_licences.RECORD_NOTE, (
        "the committed note and the note `--record` writes have drifted; "
        "the next refresh will rewrite it")


def _positions(**database):
    """A full `read_all` result with the O*NET database fields overridden."""
    base = {
        "source": lp.ONET_DATABASE, "version": "30.1",
        "licence": "L", "attribution": "A", "modification": "M",
        "applies_only_to": "This license applies only to X",
        "names_crosswalks_page": False, "read_or_measured": "read"}
    return {"onet_database": {**base, **database},
            "onet_crosswalks": {"licence": "CC BY 4.0",
                                "files_this_repo_reads": ["a", "b"],
                                "read_or_measured": "read"},
            "urban_portal": {"licence": "ODC-By", "citation": "C",
                             "read_or_measured": "read"}}


def test_the_crosswalks_line_reads_the_recorded_answer_not_a_second_reading(
        monkeypatch, capsys):
    """It computed the boolean a second time from the same string.

    `licence_positions` records `names_crosswalks_page` so the claim this
    whole document turns on is decided once. Deriving it again in the
    reporting path lets the console and the record disagree — and the console
    is what a person reads.

    The two are driven APART here: the recorded answer says the page is named,
    the string it was derived from does not say so. A re-derivation prints the
    opposite of the record.
    """
    monkeypatch.setattr(probe_licences, "read_all",
                        lambda: _positions(names_crosswalks_page=True,
                                           applies_only_to="mentions nothing"))
    probe_licences.probe()
    printed = capsys.readouterr().out
    assert "the crosswalks page IS on that list" in printed, (
        "the reporting path re-derived the answer instead of reading the "
        "recorded one, so it contradicts the record")


def test_the_modification_obligation_is_shown_not_only_recorded(
        monkeypatch, capsys):
    """The only ongoing compliance duty either page states.

    It was extracted a round earlier because the page quoted it with nothing
    behind it — and then never printed, so someone running the probe to find
    out what they owe was told everything except the thing they owe.
    """
    monkeypatch.setattr(
        probe_licences, "read_all",
        lambda: _positions(modification="[Your name] has modified this."))
    probe_licences.probe()
    assert "[Your name] has modified this." in capsys.readouterr().out

