"""`python -m etl.load_education` — its flags, its refusals, its record.

Split from `tests/test_load_education.py` at the 500-line review limit, and
split by SUBJECT: that file asks what a load DOES, this one asks what the
command does with the arguments it was given. They fail differently — a wrong
load writes a wrong graph, a wrong flag writes the wrong graph correctly.

**The wiring was asserted nowhere before this file.** Every test that called
`main` monkeypatched `load`, so inverting `only_awarded=not args.all_rows`
left the whole suite green: a flag doing the opposite of its help text would
have shipped clean.

Nothing here needs an engine.
"""

from __future__ import annotations


import pytest

from etl import load_education as loader


class Recorder:
    """Every statement the loader would send, in order, with scripted answers."""

    def __init__(self, answers=None):
        self.sent: list[str] = []
        self.answers = answers or {}

    def run(self, statement: str):
        self.sent.append(statement)
        for fragment, reply in self.answers.items():
            if fragment in statement:
                return reply
        return {"records": []}


def test_a_missing_download_says_which_command_produces_it(tmp_path,
                                                           monkeypatch):
    """`data/` is gitignored, so a fresh clone has none of it. A stack trace
    from a missing file sends the reader nowhere."""
    monkeypatch.setattr(loader, "CACHE", tmp_path)
    with pytest.raises(loader.Missing, match="download_education"):
        loader.held("completions")


def test_a_partial_load_is_refused_as_a_record(monkeypatch, tmp_path):
    """**A record of a partial load, filed where the card reads the whole
    one, is a wrong figure that looks measured.** `--limit 100` and the full
    slice write the same filename, and nothing downstream could tell them
    apart. Refused rather than written with a caveat nobody reads."""
    monkeypatch.setattr(loader, "RECORD", tmp_path / "spine.json")
    monkeypatch.setattr(loader, "load", lambda *a, **k: {
        "seconds": 1.0, "statements_issued": 1, "nodes_and_edges_created": 1,
        "already_present": 0, "institutions_in": 1, "programmes_in": 1,
        "completions_in": 1, "rows_skipped_zero_awards": 0,
        "duplicate_rows_skipped": 0})
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {})
    monkeypatch.setattr(loader, "Engine", lambda url, graph=None: Recorder())
    for partial in (["--dry-run"], ["--limit", "100"], ["--all-rows"]):
        assert loader.main(["--record", *partial]) == 4, partial
        assert not (tmp_path / "spine.json").exists()


def test_the_record_keeps_issued_and_held_apart(monkeypatch, tmp_path):
    """Two figures, stored separately, because they are two claims. Merged
    into one, the gap that caught the non-idempotent edge writes could not be
    reconstructed by anyone reading the record later."""
    written = {}
    monkeypatch.setattr(loader, "RECORD", tmp_path / "spine.json")
    monkeypatch.setattr(loader, "write_record",
                        lambda path, payload: written.update(payload))
    monkeypatch.setattr(loader, "load", lambda *a, **k: {
        "seconds": 2.0, "statements_issued": 9, "nodes_and_edges_created": 6,
        "already_present": 3, "institutions_in": 1, "programmes_in": 1,
        "completions_in": 2, "rows_skipped_zero_awards": 4,
        "duplicate_rows_skipped": 0})
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {
        "Institution": 1, "Programme": 1, "Completion": 2, "AT": 2, "IN": 2})
    monkeypatch.setattr(loader, "Engine", lambda url, graph=None: Recorder())
    assert loader.main(["--record"]) == 0
    assert written["issued"]["completions_in"] == 2
    assert written["in_graph"]["Completion"] == 2
    assert written["engine_version_reported"], (
        "the record does not say which engine answered, so a figure taken "
        "from a different build reads as one from this one")


def test_the_record_carries_the_idempotence_run_not_just_the_first(monkeypatch,
                                                                   tmp_path):
    """**The page claimed "175,762 statements, zero created" and that figure
    was in no record.** It came from a run done by hand, on a page whose
    opening sentence says every figure was substituted from the record.

    A second pass is the only way that claim can be true, and it is the claim
    the loader's whole design rests on — the first version created 2,000
    duplicate edges on a second run and only the gap column showed it.
    """
    written = {}
    monkeypatch.setattr(loader, "RECORD", tmp_path / "spine.json")
    monkeypatch.setattr(loader, "write_record",
                        lambda path, payload: written.update(payload))
    monkeypatch.setattr(loader, "Engine", lambda url, graph=None: Recorder())

    runs = iter([
        {"seconds": 10.0, "statements_issued": 6, "nodes_and_edges_created": 3,
         "already_present": 0, "institutions_in": 1, "programmes_in": 1,
         "completions_in": 1, "rows_skipped_zero_awards": 0,
         "duplicate_rows_skipped": 0, "created_by": {}, "rate_curve": []},
        {"seconds": 4.0, "statements_issued": 3, "nodes_and_edges_created": 0,
         "already_present": 3, "institutions_in": 1, "programmes_in": 1,
         "completions_in": 1, "rows_skipped_zero_awards": 0,
         "duplicate_rows_skipped": 0, "created_by": {}, "rate_curve": []},
    ])
    monkeypatch.setattr(loader, "load", lambda *a, **k: next(runs))
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {"Completion": 1})

    assert loader.main(["--record"]) == 0
    assert "second_run" in written, (
        "the record describes one pass, so the idempotence figure the page "
        "quotes has no run behind it")
    assert written["second_run"]["nodes_and_edges_created"] == 0
    assert written["second_run"]["statements_issued"] == 3


def test_every_flag_reaches_load_as_the_help_text_says(monkeypatch):
    """**The wiring was asserted nowhere.** Every test that calls `main`
    monkeypatches `loader.load`, so inverting `only_awarded=not args.all_rows`
    to `only_awarded=args.all_rows` left the suite green — a flag doing the
    opposite of its help text would have shipped clean. Mutation-verified.
    """
    seen = {}
    monkeypatch.setattr(loader, "Engine", lambda url, graph=None: Recorder())
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {})
    monkeypatch.setattr(loader, "report", lambda *a: [])
    monkeypatch.setattr(loader, "load", lambda engine, **kw: seen.update(kw) or {
        "seconds": 1.0, "statements_issued": 0, "nodes_and_edges_created": 0,
        "already_present": 0, "institutions_in": 0, "programmes_in": 0,
        "completions_in": 0, "rows_skipped_zero_awards": 0,
        "duplicate_rows_skipped": 0, "created_by": {}, "rate_curve": []})

    loader.main([])
    assert seen["only_awarded"] is True, "the default drops zero-award rows"
    assert seen["dry_run"] is False and seen["limit"] is None

    seen.clear()
    loader.main(["--all-rows"])
    assert seen["only_awarded"] is False, (
        "--all-rows must LOAD the zero-award rows, which is the opposite of "
        "only_awarded")

    seen.clear()
    loader.main(["--dry-run", "--limit", "7"])
    assert seen["dry_run"] is True and seen["limit"] == 7


def test_the_graph_flag_reaches_the_engine(monkeypatch):
    """**Without it the spine went to `default` while the district goes to
    `edtech`** — two disconnected halves, and the cross-tier join they exist
    for cannot be written across them. `etl/load_pwcs.py` defaults to
    `edtech`; so does this now."""
    asked = {}
    monkeypatch.setattr(loader, "Engine",
                        lambda url, graph=None: asked.update(
                            url=url, graph=graph) or Recorder())
    monkeypatch.setattr(loader, "in_the_graph", lambda e: {})
    monkeypatch.setattr(loader, "report", lambda *a: [])
    monkeypatch.setattr(loader, "load", lambda engine, **kw: {
        "seconds": 1.0, "statements_issued": 0, "nodes_and_edges_created": 0,
        "already_present": 0, "institutions_in": 0, "programmes_in": 0,
        "completions_in": 0, "rows_skipped_zero_awards": 0,
        "duplicate_rows_skipped": 0, "created_by": {}, "rate_curve": []})
    loader.main([])
    assert asked["graph"] == "edtech", (
        "the loader writes a different graph from etl/load_pwcs.py")
    loader.main(["--graph", "somewhere-else"])
    assert asked["graph"] == "somewhere-else"


def test_record_with_limit_zero_is_refused_before_the_load(monkeypatch,
                                                           capsys):
    """**The same truthiness bug, 200 lines from where it was fixed.**
    `if args.limit:` read `--limit 0` as "no limit", so `--record --limit 0`
    passed the guard, recorded a load of zero completions, and then re-ran
    without a limit — writing a record the doc tests contradict.

    And it is refused BEFORE the load: the guard used to sit after `load()`
    returned, so a `--record --limit 100` spent forty minutes and then
    declined to write.
    """
    ran = []
    monkeypatch.setattr(loader, "Engine", lambda url, graph=None: Recorder())
    monkeypatch.setattr(loader, "load",
                        lambda *a, **k: ran.append(1) or {})
    for partial in (["--limit", "0"], ["--limit", "100"], ["--dry-run"],
                    ["--all-rows"]):
        assert loader.main(["--record", *partial]) == 4, partial
    assert not ran, "the load ran before the flags were checked"
    assert "drop --dry-run" in capsys.readouterr().err
