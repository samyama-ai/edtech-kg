"""One `USER_AGENT`, and it has to stay one.

Seventeen modules each defined their own and three distinct values were in
flight. The consolidation is only worth anything if the eighteenth probe does
not quietly start a fourth, so this is a ratchet rather than a one-off tidy.

The stakes are not cosmetic. A publisher who blocks one agent is not blocking
the others, so a refusal appears in one probe and not its neighbour and reads
as a fact about the publisher. And `docs/sources/bls-occupation.md` measured
BLS answering **403** to the same name with the contact URL removed — so the
URL is load-bearing, and two of the seventeen pointed at a host this repo does
not live on.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from etl.identity import USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
ETL = sorted((ROOT / "etl").glob("*.py"))
BLS_DOC = ROOT / "docs" / "sources" / "bls-occupation.md"


def test_the_modules_are_actually_being_scanned():
    """A scan over an empty list is a green test of nothing."""
    assert len(ETL) >= 15, ETL
    assert any(p.name.startswith("probe_") for p in ETL)


def test_only_one_module_defines_the_agent():
    """The ratchet. Assign in a second module and this names the file."""
    defining = []
    for path in ETL:
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target] if isinstance(node, ast.AnnAssign)
                       else [])
            if any(isinstance(t, ast.Name) and t.id == "USER_AGENT"
                   for t in targets):
                defining.append(path.name)
    assert defining == ["identity.py"], (
        f"USER_AGENT is defined in {defining}; it belongs only in "
        f"etl/identity.py, and a second definition is how a publisher ends up "
        f"blocking one probe and not its neighbour")


def test_no_module_sends_an_agent_string_it_wrote_itself():
    """The other direction. A module can bypass the constant entirely by
    putting a literal in the header dict, which the check above cannot see."""
    offenders = []
    for path in ETL:
        if path.name == "identity.py":
            continue
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r'"User-Agent"\s*:\s*["\']', line):
                offenders.append(f"{path.name}:{number}: {line.strip()[:70]}")
    assert not offenders, (
        f"these send a hand-written agent rather than the shared one: {offenders}")


@pytest.mark.parametrize("part", ["edtech-kg", "https://git.samyama.ai/"])
def test_the_agent_carries_a_name_and_a_reachable_contact_url(part):
    """Both halves are load-bearing — the name so a publisher's logs say who
    this was, the URL so they can find out why. Two of the seventeen
    advertised `github.com/samyama-ai/edtech-kg`, which is not where this repo
    lives; an address nobody can reach is closer to the 403 case that document
    measured than to the 200 one."""
    assert part in USER_AGENT, USER_AGENT


def test_the_document_quotes_the_agent_that_is_actually_sent():
    """`bls-occupation.md` publishes the agent BLS answered 200 to. If the
    constant changes and that row does not, the page is reporting a
    measurement of a string nothing sends."""
    doc = BLS_DOC.read_text(encoding="utf-8")
    quoted = re.search(r"^\| Ours — `([^`]+)`", doc, re.M)
    assert quoted, "bls-occupation.md no longer quotes the agent it measured"
    # The row abbreviates the URL with an ellipsis, so the NAME is what is
    # compared — matching the whole string would fail on a formatting choice
    # rather than on a drift that matters.
    name = quoted.group(1).split(" (+")[0]
    assert USER_AGENT.startswith(name), (
        f"the document measured {name!r} and the code now sends "
        f"{USER_AGENT!r}")
