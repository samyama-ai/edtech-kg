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
    probe.probe(sample=50)
    assert "distinct publishers" in capsys.readouterr().out


def test_both_probes_print_the_same_prerequisite_table(capsys):
    """probe_ctdl kept its own copy and it had already drifted — missing the
    stated-but-empty and publisher-spread lines. One printer, so it cannot."""
    import inspect
    from etl import probe_ctdl
    assert "print_prerequisites" in inspect.getsource(probe_ctdl)
    assert "stating a prerequisite" not in inspect.getsource(probe_ctdl), "a second copy"


def test_both_probes_share_one_command_line():
    """The two main() functions were byte-identical, which is how probe_ctdl
    kept type=int and no MalformedSource handler for a round after
    probe_registry gained both."""
    import inspect
    from etl import probe_ctdl
    assert "run_cli(" in inspect.getsource(probe_ctdl.main)
    assert "add_argument" not in inspect.getsource(probe_ctdl.main)
