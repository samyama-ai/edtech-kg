"""Every measured record says which code produced it.

`DATASET-CARD.md` claimed the code version was "this repository, at the commit
that produced the records". Nothing recorded that commit — twelve records, none
carrying one — so the claim could not be checked and a figure in `docs/sources/`
could not be traced to the code that printed it.

That is the same shape this repo keeps finding: a claim in prose with nothing
behind it. These tests are the "behind it".
"""

from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

import pytest

from etl import provenance
from etl.provenance import code_version, write_record

ROOT = Path(__file__).resolve().parent.parent
#: Every module that writes a record — not every module named `probe_*`.
#: Globbing the prefix missed `registry_licence.py` and `sweep_prerequisites.py`,
#: which write two of the twelve records in docs/sources/. So the guard against
#: an unstamped record had a hole exactly where the two unstamped records were,
#: and the PR claiming "every record" was true of ten. The `RECORD` skip below
#: filters the modules that write nothing.
WRITERS = sorted((ROOT / "etl").glob("*.py"))


def test_the_stamp_says_what_it_can_and_admits_what_it_cannot():
    got = code_version()
    assert set(got) >= {"commit", "dirty", "package"}
    # `dirty` is a tri-state on purpose: None means git did not answer, which is
    # not the same as a clean tree, and recording it as False would be a claim.
    assert got["dirty"] in (True, False, None)


def test_a_silent_git_becomes_unknown_rather_than_empty(monkeypatch):
    """`assert commit != ""` could never fail — `commit or "unknown"` makes it
    non-empty by construction, so the assertion described a guarantee the line
    above it already provided and tested nothing. The behaviour worth asserting
    is what happens when git says nothing, and that needs git stubbed."""
    monkeypatch.setattr(provenance, "_git", lambda *a: None)
    provenance._code_version.cache_clear()
    try:
        got = provenance.code_version()
        assert got["commit"] == "unknown"
        assert got["dirty"] is None, (
            "a git that did not answer is not a clean tree")
    finally:
        provenance._code_version.cache_clear()


def test_write_record_stamps_the_code():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.json"
        write_record(path, {"value": 1})
        got = json.loads(path.read_text(encoding="utf-8"))
        assert got["value"] == 1
        assert got["code"]["commit"] == code_version()["commit"]


def test_a_payload_cannot_overwrite_its_own_provenance():
    """The stamp goes on last. A probe carrying its own `code` key would
    otherwise replace the provenance with something that is not it, silently."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.json"
        write_record(path, {"code": "not the provenance"})
        got = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(got["code"], dict) and "commit" in got["code"]


def test_records_keep_their_characters():
    """Three of the eleven probes wrote without `ensure_ascii=False`, so an
    em-dash came out as an escape in some records and as the character in
    others — for no reason anyone chose. One writer, one answer."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "r.json"
        write_record(path, {"note": "an em—dash"})
        assert "em—dash" in path.read_text(encoding="utf-8")


#: Records written before this mechanism existed. **This list may only shrink.**
#: A file here that HAS a stamp fails — otherwise re-running a probe and
#: forgetting to delete the entry leaves the list looking like work still to do,
#: and a shrinking list nobody shrinks is a cap rather than a ratchet.
UNSTAMPED = {
    "ceds-measured.json",
    "education-measured.json",
    "engine-capability-measured.json",
    "federal-direct-measured.json",
    "institution-identity-measured.json",
    "licences-measured.json",
    "pathway-identity-measured.json",
    "registry-licence-measured.json",
    "review-cost-measured.json",
    "sced-measured.json",
    "state-access-measured.json",
    "vocabularies-measured.json",
}

RECORDS = sorted((ROOT / "docs" / "sources").glob("*.json"))


@pytest.mark.parametrize("record", RECORDS, ids=lambda p: p.name)
def test_a_committed_record_is_stamped_or_listed_as_not(record):
    """DATASET-CARD says records carry a `code` stamp. Nothing checked that.

    The mechanism landed, the card was reworded to claim the outcome, and every
    one of the twelve committed records had no stamp — a claim in prose with
    nothing behind it, one line above where that exact failure was removed. The
    guard on the writers could not catch it: it reads probe source, never the
    records.
    """
    got = json.loads(record.read_text(encoding="utf-8"))
    stamp = got.get("code")

    if record.name in UNSTAMPED:
        assert stamp is None, (
            f"{record.name} now carries a stamp — delete it from UNSTAMPED. "
            f"The list is a ratchet and may only shrink.")
        pytest.skip(f"{record.name} predates the stamp; it gains one when "
                    f"`{record.stem.replace('-measured', '')}` is next run")

    assert isinstance(stamp, dict), (
        f"{record.name} carries no `code` stamp and is not listed in "
        f"UNSTAMPED — DATASET-CARD says records carry one")
    assert set(stamp) >= {"commit", "dirty", "package"}, (
        f"{record.name} has a `code` key that is not a provenance stamp: "
        f"{sorted(stamp)}")


def test_the_unstamped_list_names_records_that_exist():
    """A list naming a deleted file silently stops guarding anything."""
    present = {r.name for r in RECORDS}
    missing = sorted(UNSTAMPED - present)
    assert not missing, (
        f"UNSTAMPED names records that are not in docs/sources/: {missing}")


@pytest.mark.parametrize("probe", WRITERS, ids=lambda p: p.name)
def test_every_probe_that_writes_a_record_goes_through_the_stamped_writer(probe):
    """Asserted against the call, not against the import.

    An import proves nothing — eleven probes imported `code_version` and never
    called it, and nothing in this suite noticed. What matters is that the
    write goes through the one function that stamps.
    """
    source = probe.read_text(encoding="utf-8")
    tree_ = ast.parse(source)
    has_record = any(
        isinstance(n, ast.Assign) and any(
            isinstance(t_, ast.Name) and t_.id == "RECORD" for t_ in n.targets)
        for n in tree_.body)
    if not has_record:
        pytest.skip(f"{probe.name} defines no module-level RECORD")

    tree = ast.parse(source)
    # Any write to RECORD, not just `.write_text`. Matching one method name
    # let `write_bytes`, `open("w")` and a local alias through — a guard that
    # catches the shape it was written against and nothing else.
    WRITE_METHODS = {"write_text", "write_bytes", "open"}
    writes_direct = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in WRITE_METHODS
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "RECORD"]
    # `open(RECORD, "w")` and `json.dump(..., RECORD.open("w"))` too.
    writes_direct += [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "open"
        and any(isinstance(a, ast.Name) and a.id == "RECORD" for a in n.args)]
    assert not writes_direct, (
        f"{probe.name} writes RECORD directly; use write_record() so the "
        f"record says which code produced it")

    stamped = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "write_record"]
    assert stamped, f"{probe.name} has a RECORD but never calls write_record()"
