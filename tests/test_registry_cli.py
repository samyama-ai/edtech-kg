"""The command line both probes share, and what it prints.

Split out of `tests/test_probe_registry.py` for #86. Split by SUBJECT: this
file covers the entry points — argument rejection, exit codes, and the tables
that are printed rather than returned — for `probe_registry` and `probe_ctdl`
together, because the two run one `run_cli` and print one prerequisite table.

Kept in one file deliberately. That the two probes print the same table from
the same code is the property under test; asserting it from inside either
probe's own file would let them drift apart and still pass.
"""

import argparse

import pytest

from etl import probe_ctdl
from etl import probe_registry as probe
from etl import registry_read as read
from tests.registry_stubs import course, paged


def test_asking_for_zero_or_fewer_courses_is_rejected_by_the_cli():
    """It used to build per_page=0 and then fail with "no course records
    returned", blaming the source for a bad argument. Then it raised inside
    sample_pages and exited under "refused" — the category this module reserves
    for figures it declines to report. Bad CLI input is argparse's job."""
    for bad in ("0", "-5"):
        with pytest.raises(argparse.ArgumentTypeError, match="at least 1"):
            probe.positive(bad)


def test_the_cli_rejects_it_before_any_request_is_made(monkeypatch):
    """Nothing should be fetched to discover that an argument is invalid."""
    monkeypatch.setattr(read.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("fetched despite bad input"))
    with pytest.raises(SystemExit) as exit_code:
        probe.main(["--courses", "0"])
    assert exit_code.value.code == 2        # argparse usage error


def test_a_corrupt_body_exits_three_through_main(monkeypatch):
    monkeypatch.setattr(probe, "registry_totals", lambda: {"source": "x"})
    monkeypatch.setattr(probe, "course_prerequisites",
                        lambda sample: (_ for _ in ()).throw(read.MalformedSource("bad")))
    assert probe.main([]) == 3


def test_the_publisher_spread_is_printed_not_only_in_json(monkeypatch, capsys):
    """The docstring says publisher spread is reported alongside the rate, and
    the document quotes "13 distinct publishers" — but only --json carried it."""
    paged(monkeypatch, {1: [course()]})
    monkeypatch.setattr(probe, "registry_totals", lambda: {
        "source": "x", "envelopes_root": 1, "resources_all_communities": 1,
        "communities": {}, "ce_registry_by_type": {}, "deleted_resources": 0,
        "provisional_resources": 0, "unattributed": 0,
        "secured_communities": [], "failed_communities": []})
    result = probe.probe(sample=50)

    printed = capsys.readouterr().out
    counted = result["course_prerequisites"]["distinct_publishers"]
    # The COUNT, not just the label. Asserting the caption alone passes whether
    # the number beside it is right, absent, or zero — and the caption is the
    # half nothing depends on.
    assert f"{counted:,} distinct publishers" in printed, printed

    # 1, and worth stating why: this stub's course carries no publisher, and
    # `course_prerequisites` folds a missing one into an "unknown" sentinel
    # that then counts as a distinct publisher. So the published "13 distinct
    # publishers" may include "unknown" as one of the 13 — the same species as
    # the NO MATCH sentinel counted in #70. Pinned here so the behaviour is
    # recorded rather than assumed; changing it is a probe change, not a
    # file-splitting one.
    assert counted == 1, result["course_prerequisites"]


def test_both_probes_print_the_same_prerequisite_table():
    """probe_ctdl kept its own copy and it had already drifted — missing the
    stated-but-empty and publisher-spread lines. One printer, so it cannot.

    Asserted by IDENTITY rather than by searching probe_ctdl's source for a
    phrase the other printer happens to use. A phrase search is a
    false-negative trap: reword the table and the negative assertion passes for
    ever afterwards while a second copy sits there. Two names bound to one
    function object cannot drift, and the check does not care what either
    prints."""
    assert probe_ctdl.print_prerequisites is probe.print_prerequisites
    assert probe_ctdl.print_registry is probe.print_registry


def test_both_probes_share_one_command_line():
    """The two main() functions were byte-identical, which is how probe_ctdl
    kept type=int and no MalformedSource handler for a round after
    probe_registry gained both.

    One shared `run_cli` object, checked by identity, plus the behaviour that
    matters: both reject a bad argument the same way, before any request. A
    second parser would pass a source search for "run_cli(" and still diverge
    here."""
    assert probe_ctdl.run_cli is probe.run_cli

    for entry in (probe.main, probe_ctdl.main):
        with pytest.raises(SystemExit) as exit_code:
            entry(["--courses", "0"])
        assert exit_code.value.code == 2, entry
