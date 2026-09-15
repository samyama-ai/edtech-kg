"""Shared fixtures for the national-spine loader's tests.

Split out when `tests/test_cip_key.py` needed the same three helpers as
`tests/test_load_education.py`. Two copies of a recorder is how they drift
into disagreeing about what the engine answered, which is the same argument
`tests/graph_stub.py` already makes.
"""

from __future__ import annotations

import json

from etl import load_education as loader


class Recorder:
    """Every statement the loader would send, in order, with scripted answers."""

    def __init__(self, answers=None, url="http://engine.test"):
        self.sent: list[str] = []
        self.answers = answers or {}
        # Named, because refusals quote it: a message saying which engine
        # would not answer is the difference between a bug report and a shrug.
        self.url = url

    def scalar(self, statement: str):
        """One value, the way `Engine.scalar` answers it.

        Added when the loader grew a guard that reads a count back before
        writing: without it the stub raised `AttributeError` and the guard
        looked broken rather than uncovered.
        """
        rows = (self.run(statement) or {}).get("records") or []
        return rows[0][0] if rows and rows[0] else None

    def run(self, statement: str):
        self.sent.append(statement)
        for fragment, reply in self.answers.items():
            if fragment in statement:
                return reply
        return {"records": []}


def slice_on_disk(tmp_path, rows, institutions=None):
    """Write a cache this loader will read, and return its directory."""
    (tmp_path / f"institutions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": institutions if institutions is not None
                    else [{"unitid": 1, "inst_name": "X", "state_abbr": "VA"}]}),
        encoding="utf-8")
    (tmp_path / f"completions-{loader.FIPS}-{loader.YEAR}.json").write_text(
        json.dumps({"rows": rows}), encoding="utf-8")
    return tmp_path


def completions(n, first=0, **over):
    """`n` rows with DISTINCT keys, starting at `first`.

    `first` exists because a fixture that reused CIP codes across two calls
    made the zero-award rows collide with the awarded ones — so a test about
    zero-award skipping was measuring duplicate-key skipping as well, and
    passed for the wrong reason.
    """
    return [{"unitid": 1, "cipcode_6digit": 110701 + first + i,
             "award_level": 5, "majornum": 1, "race": 1, "sex": 1,
             "awards_6digit": 1, **over}
            for i in range(n)]
