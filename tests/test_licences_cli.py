"""`python -m etl.probe_licences` — the CLI, the console, and the record.

Split from `tests/test_licences_doc.py` when that file passed the 500-line
review limit. Split by SUBJECT: this file drives `main` and `probe` and reads
what they print and write. That file checks the published document against the
committed record.

The reporting path is over-represented here on purpose. It is the one place a
defect is invisible to every assertion and visible to every user, and three
have shipped from it: a lint fix that printed a variable name, a rename that
crashed the documented command, and a value derived twice that let the console
contradict the record.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from etl import licence_positions as lp
from etl import probe_licences
from tests.test_licence_positions import (CROSSWALKS_PAGE, DATABASE_PAGE,
                                          URBAN_PAGE)


ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "licences-measured.json"


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


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


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


def test_the_message_names_the_repo_path_for_a_record_inside_the_repo(
        monkeypatch, capsys):
    """The branch that runs in production was the untested one.

    Every other test points `RECORD` at a `tmp_path`, which is OUTSIDE `ROOT`,
    so only the fallback ran — replacing the `is_relative_to`-true branch with
    a wrong string left the whole suite green. The old assertion on the
    literal "docs/sources/out.json" was wrong for its reason, but it did pin
    the prefix a real `--record` prints, and nothing pinned it after that.
    """
    monkeypatch.setattr(probe_licences, "read_all", _positions)
    destination = probe_licences.ROOT / "docs" / "sources" / "x-test.json"
    monkeypatch.setattr(probe_licences, "RECORD", destination)
    try:
        assert probe_licences.main(["--record"]) == 0
        assert "wrote docs/sources/x-test.json" in capsys.readouterr().out
    finally:
        destination.unlink(missing_ok=True)


def test_the_sced_record_message_survives_an_unrelated_working_directory(
        monkeypatch, tmp_path, capsys):
    """`probe_sced` derived the same message from the CWD rather than the repo.

    `relative_to` raises when its argument is not an ancestor, so this crashed
    from any directory outside the repo — and it crashed AFTER the write
    landed, leaving a correct record and a traceback. It went unnoticed
    because the directories people run from happen to be ancestors.
    """
    import os

    from etl import probe_sced

    monkeypatch.setattr(probe_sced, "probe",
                        lambda quiet=False: {"new_york": {}, "district": {}})
    monkeypatch.setattr(probe_sced, "record", lambda a, b: {"x": 1})
    root = pathlib.Path(probe_sced.__file__).resolve().parents[1]
    destination = root / "docs" / "sources" / "x-sced-test.json"
    monkeypatch.setattr(probe_sced, "RECORD", destination)

    here = os.getcwd()
    os.chdir(tmp_path)                     # not an ancestor of the repo
    try:
        # DRIVEN, not reimplemented. The first version of this recomputed the
        # path expression in the test and asserted on its own arithmetic, so
        # reverting the fix left it green — a test of the test.
        assert probe_sced.main(["--record"]) == 0
        assert "wrote docs/sources/x-sced-test.json" in capsys.readouterr().out
    finally:
        os.chdir(here)
        destination.unlink(missing_ok=True)
