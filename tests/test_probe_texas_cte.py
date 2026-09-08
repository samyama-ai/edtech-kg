"""What the Texas probe reports, without touching the network.

`measure()` takes bytes, so every case here builds a zip in memory. Nothing
below reaches TEA, and none of it is a re-run of the live measurement — that
lives in `docs/sources/texas-cte-measured.json`.
"""

from __future__ import annotations

import io
import json
import pathlib
import zipfile

import pytest

from etl import probe_texas_cte as probe

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "sources" / "texas-cte-measured.json"

HEADER = ("Code,Translation,Eligible for State HS Credit,Course Abbreviation,"
          "Course Units,CTE Course,Subject,Subject Area")


def archive(**files: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            z.writestr(name.replace("_", ".") if name.endswith("_csv")
                       else name, body)
    return buf.getvalue()


def courses(*rows: str) -> bytes:
    return archive(**{"C022.csv": HEADER + "\n" + "\n".join(rows) + "\n"})


def test_a_missing_course_table_refuses_rather_than_reporting_zero():
    """An empty count over a download that does not hold the table reads as
    "Texas publishes no CTE courses", which is a wrong finding."""
    with pytest.raises(SystemExit, match="C022.csv"):
        probe.measure(archive(**{"C999.csv": "Code,Translation\n01,x\n"}))


def test_any_non_blank_flag_counts_as_cte():
    """The values are H and M today. Freezing that list means a new value —
    say E for elementary — is recorded in the histogram and silently dropped
    from the count, so the doc's figure still reads as measured."""
    got = probe.measure(courses(
        "01,Alpha,1,A,1,H, , ",
        "02,Beta,1,B,1,M, , ",
        "03,Gamma,1,C,1,E, , ",      # a value this run has never seen
        "04,Delta,0,D,0, , , ",
    ))
    assert got["courses"]["cte_courses"] == 3, (
        "a flag value the probe has not seen before must still count")
    assert got["courses"]["cte_flag_values"]["E"] == 1, (
        "and the histogram must carry it, so the change is visible")


def test_the_cluster_columns_are_counted_not_assumed():
    got = probe.measure(courses(
        "01,Alpha,1,A,1,H,Agriculture,Ag Science",
        "02,Beta,1,B,1,H, , ",
    ))
    assert got["cluster_columns_populated"] == {"Subject": 1, "Subject Area": 1}


def test_a_real_code_is_not_labelled_a_false_positive_by_the_program():
    """`report()` used to print "checked by hand — statute refs, not codes"
    over whatever the run had matched, so a genuine CIP code would have been
    labelled a false positive by the program rather than by a reader."""
    got = probe.measure(archive(**{
        "C022.csv": HEADER + "\n01,Alpha,1,A,1,H, , \n",
        "C500.csv": "Code,Translation\n01,Welding 51.0618\n",
    }))
    found = got["code_shaped_matches"]["C500.csv"]
    assert found["cip_shaped"] == 1
    assert "51.0618" in found["samples"], (
        "the matched strings must be recorded, or the 'they are all statute "
        "references' verdict cannot be re-checked from the record")


def test_soc_is_searched_across_every_table_not_just_the_courses():
    got = probe.measure(archive(**{
        "C022.csv": HEADER + "\n01,Alpha,1,A,1,H, , \n",
        "C700.csv": "Code,Translation\n01,Welder 51-4121\n",
    }))
    assert got["code_shaped_matches"]["C700.csv"]["soc_shaped"] == 1


def test_the_committed_record_is_shaped_the_way_the_doc_reads_it():
    got = json.loads(RECORD.read_text(encoding="utf-8"))
    assert got["courses"]["rows"] > 0
    assert set(got) >= {"retrieved_at", "source", "tables_in_download",
                        "courses", "cluster_columns_populated",
                        "code_shaped_matches"}
