"""Tests for the College Scorecard probe.

The network and the archive are stubbed. Under test: the two suppression
markers, which a first pass guessed wrong and reported 100% coverage from; the
discovered download link; and reading the cohort definition rather than
remembering it.
"""

import csv
import io
import json
import urllib.error
import zipfile
from pathlib import Path

import pytest

from etl import probe_scorecard as probe


COLUMNS = ["UNITID", "INSTNM", "CIPCODE", "CIPDESC", "CREDLEV", "CREDDESC",
           *probe.HORIZONS]


def record(unitid="1", cip="11.0101", level="3", label="Bachelor's Degree", **earnings):
    row = dict.fromkeys(COLUMNS, "NA")
    row.update(UNITID=unitid, INSTNM="A College", CIPCODE=cip,
               CIPDESC="A programme", CREDLEV=level, CREDDESC=label)
    row.update(earnings)
    return row


def archive(tmp_path: Path, records) -> Path:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS)
    writer.writeheader()
    for row in records:
        writer.writerow(row)
    path = tmp_path / "fos.zip"
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("Most-Recent-Cohorts-Field-of-Study.csv", buffer.getvalue())
    return path


# --------------------------------------------------------------------------
# the suppression markers — where a first pass reported 100%
# --------------------------------------------------------------------------

def test_a_suppressed_value_is_not_a_published_figure(tmp_path):
    """`PS` means too few students to publish. It is not blank, so anything
    testing for emptiness counts it as a figure — which is how a first pass
    reported 100% coverage of a field that is mostly suppressed."""
    path = archive(tmp_path, [record(EARN_MDN_4YR="PS")])
    got = probe.coverage(path)["horizons"]["EARN_MDN_4YR"]
    assert got["published"] == 0
    assert got["suppressed"] == 1


def test_a_not_applicable_value_is_counted_separately(tmp_path):
    """`NA` and `PS` are different facts: nothing to report, versus something
    withheld. Folding them together hides which."""
    path = archive(tmp_path, [record(EARN_MDN_4YR="NA")])
    got = probe.coverage(path)["horizons"]["EARN_MDN_4YR"]
    assert (got["published"], got["suppressed"], got["not_applicable"]) == (0, 0, 1)


def test_a_real_figure_is_counted(tmp_path):
    path = archive(tmp_path, [record(EARN_MDN_4YR="48200")])
    got = probe.coverage(path)["horizons"]["EARN_MDN_4YR"]
    assert got["published"] == 1
    assert got["share"] == 100.0


def test_the_share_is_of_all_rows_not_of_non_suppressed(tmp_path):
    """Reporting "of those published" would make a mostly-suppressed field look
    complete."""
    path = archive(tmp_path, [record(EARN_MDN_4YR="48200"),
                              record(EARN_MDN_4YR="PS"),
                              record(EARN_MDN_4YR="PS"),
                              record(EARN_MDN_4YR="NA")])
    assert probe.coverage(path)["horizons"]["EARN_MDN_4YR"]["share"] == 25.0


# --------------------------------------------------------------------------
# credential levels — labelled by the file, not by us
# --------------------------------------------------------------------------

def test_credential_labels_come_from_the_file(tmp_path):
    """Naming the levels in the probe produced a table saying Bachelor's had
    1,249 rows. Wrong, and plausible enough to ship."""
    path = archive(tmp_path, [
        record(level="2", label="Associate's Degree", EARN_MDN_4YR="30000"),
        record(level="3", label="Bachelor's Degree", EARN_MDN_4YR="PS")])
    levels = probe.coverage(path)["by_credential_level"]
    assert levels["2"]["label"] == "Associate's Degree"
    assert levels["3"]["label"] == "Bachelor's Degree"


def test_coverage_is_reported_per_credential_level(tmp_path):
    """The headline share hides that the levels a student without four years
    would choose have the worst coverage."""
    path = archive(tmp_path, [
        record(level="1", EARN_MDN_4YR="PS"),
        record(level="1", EARN_MDN_4YR="PS"),
        record(level="3", EARN_MDN_4YR="52000")])
    levels = probe.coverage(path)["by_credential_level"]
    assert levels["1"]["share"] == 0.0
    assert levels["3"]["share"] == 100.0


def test_an_empty_file_is_refused(tmp_path):
    path = archive(tmp_path, [])
    with pytest.raises(ValueError, match="refusing"):
        probe.coverage(path)


def test_an_archive_without_a_csv_is_malformed(tmp_path):
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as book:
        book.writestr("readme.txt", "nothing here")
    with pytest.raises(probe.MalformedSource, match="no CSV"):
        probe.coverage(path)


# --------------------------------------------------------------------------
# the download link, which carries a release date
# --------------------------------------------------------------------------

def serve(monkeypatch, payload: bytes):
    monkeypatch.setattr(probe, "fetch", lambda url: payload)


def test_the_download_link_is_discovered_not_hardcoded(monkeypatch):
    """The published link is `..._06102026.zip` and changes every release. A
    pinned URL 404s on the next publication and reads as a source problem."""
    serve(monkeypatch, b'<a href="https://x/downloads/'
                       b'Most-Recent-Cohorts-Field-of-Study_09152027.zip">data</a>')
    assert probe.field_of_study_url().endswith("_09152027.zip")


def test_a_page_without_the_link_is_malformed(monkeypatch):
    """A rename would otherwise look like missing data."""
    serve(monkeypatch, b"<html>the data has moved</html>")
    with pytest.raises(probe.MalformedSource, match="no Field-of-Study"):
        probe.field_of_study_url()


# --------------------------------------------------------------------------
# the cohort — read from the publisher, not remembered
# --------------------------------------------------------------------------

GLOSSARY = (b"<p>Median Earnings The median annual earnings of individuals who "
            b"received federal financial aid during their studies and completed an "
            b"award at the indicated field of study. To be included, the individuals "
            b"needed to be working and not be enrolled in school during the year "
            b"when earnings are measured. Median earnings are measured in the "
            b"fourth full year after the student completed their award.</p>")


def test_all_three_filters_are_read_from_the_definition(monkeypatch):
    """scope.md recorded one caveat. The published definition carries three,
    and the second — working and not enrolled — raises the figure by excluding
    the unemployed."""
    serve(monkeypatch, GLOSSARY)
    cohort = probe.cohort_definition()
    assert cohort["federal_aid_only"] is True
    assert cohort["working_and_not_enrolled"] is True
    assert cohort["measured_at"] == "fourth full year"


def test_the_definition_is_quoted_so_a_reader_can_check_it(monkeypatch):
    serve(monkeypatch, GLOSSARY)
    assert "received federal financial aid" in probe.cohort_definition()["quoted"]


def test_a_glossary_without_the_entry_is_malformed(monkeypatch):
    """Silently reporting all three filters as absent would read as "no
    caveats apply"."""
    serve(monkeypatch, b"<html>nothing about earnings</html>")
    with pytest.raises(probe.MalformedSource, match="Median Earnings"):
        probe.cohort_definition()


# --------------------------------------------------------------------------
# the CLI
# --------------------------------------------------------------------------

def test_a_missing_archive_says_how_to_get_it(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ARCHIVE", tmp_path / "absent.zip")
    assert probe.main([]) == 1


def test_an_unreachable_source_exits_two(monkeypatch):
    monkeypatch.setattr(probe, "download",
                        lambda: (_ for _ in ()).throw(RuntimeError("dns")))
    assert probe.main(["--download"]) == 2


def test_a_malformed_source_exits_three(monkeypatch):
    monkeypatch.setattr(probe, "download",
                        lambda: (_ for _ in ()).throw(probe.MalformedSource("moved")))
    assert probe.main(["--download"]) == 3


def test_json_output_carries_a_timestamp(monkeypatch, tmp_path, capsys):
    path = archive(tmp_path, [record(EARN_MDN_4YR="48200")])
    monkeypatch.setattr(probe, "ARCHIVE", path)
    monkeypatch.setattr(probe, "cohort_definition",
                        lambda: {"source": "x", "quoted": "y", "federal_aid_only": True,
                                 "working_and_not_enrolled": True,
                                 "measured_at": "fourth full year"})
    assert probe.main(["--json"]) == 0
    assert "retrieved_at" in json.loads(capsys.readouterr().out)
