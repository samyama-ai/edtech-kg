"""Fixtures for the BLS probe tests — the published table, as markup.

Split out when `tests/test_probe_bls.py` reached 545 lines and review skipped it
whole as too large to read. The parsing-and-coverage tests and the
access-and-release tests are different subjects; the table fixture was the only
thing tying them to one file.
"""

from __future__ import annotations

from etl import probe_bls as probe

HEADER = ("<TR><TH>Occupation Title</TH><TH>Occupation Code</TH>"
          "<TH>Employment 2024</TH><TH>Employment 2034</TH>"
          "<TH>Employment Change, 2024-2034</TH>"
          "<TH>Employment Percent Change, 2024-2034</TH>"
          "<TH>Occupational Openings, 2024-2034 Annual Average</TH>"
          "<TH>Median Annual Wage 2024</TH>"
          "<TH>Education, Work Experience, and Training</TH></TR>")


def row(code, title="An occupation", wage="$50,000", education="Bachelor's degree"):
    return (f"<TR><TD>{title}</TD><TD>{code}</TD><TD>100.0</TD><TD>110.0</TD>"
            f"<TD>10.0</TD><TD>10.0</TD><TD>5.0</TD><TD>{wage}</TD>"
            f"<TD>{education}</TD></TR>")


def page(*rows):
    return "<html>" + HEADER + "".join(rows) + "</html>"


def serve(monkeypatch, markup):
    monkeypatch.setattr(probe, "fetch", lambda url: markup)
