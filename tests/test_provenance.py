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
    assert got["commit"] != "", "a commit of empty string is not 'unknown'"
    # `dirty` is a tri-state on purpose: None means git did not answer, which is
    # not the same as a clean tree, and recording it as False would be a claim.
    assert got["dirty"] in (True, False, None)


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
    writes_direct = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "write_text"
        and isinstance(n.func.value, ast.Name) and n.func.value.id == "RECORD"]
    assert not writes_direct, (
        f"{probe.name} writes RECORD directly; use write_record() so the "
        f"record says which code produced it")

    stamped = [n for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "write_record"]
    assert stamped, f"{probe.name} has a RECORD but never calls write_record()"
