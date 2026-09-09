"""Run one test file under a socket watcher, in a child process.

Extracted from `tests/test_registry_probe.py`, which wrote it inline for
itself. #184 asked for the same guard on a second file and copying it would
have made two, which is how a check drifts into two checks that disagree.

**A per-file guard, not a suite-wide one.** A suite-wide backstop in a
`tests/conftest.py` is the better answer and is being built on the #179
branch; hoisting it here would put the same new file on two open branches,
and the README test-count line already taught this repo what that costs at
merge time. When that conftest lands, this helper and its two callers can go.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def connects_made_by(test_file: str) -> tuple[int, str]:
    """How many sockets the file connected, and the child's output.

    **The path is DERIVED by the caller, never written.** Hardcoding it
    survived a file rename by pointing the deselect at a module that no longer
    held the test — so the child ran it too, and it ran a child of its own,
    and the run had to be killed.

    `connect_ex` as well as `connect`. `urllib` reaches the network through
    `connect`, but a guard that watches only one of them is green against the
    other, and being able to say "no test here opened a socket" means both.
    """
    target = pathlib.Path(test_file).resolve().relative_to(ROOT).as_posix()
    watcher = f"""
import socket
hits = []
class Watch(socket.socket):
    def connect(self, addr):
        hits.append(addr)
        return super().connect(addr)
    def connect_ex(self, addr):
        hits.append(addr)
        return super().connect_ex(addr)
socket.socket = Watch
import pytest
pytest.main(['-q', '--no-header', '-p', 'no:cacheprovider',
             {target!r},
             '--deselect', {target + '::test_this_file_opens_no_sockets'!r}])
print('CONNECTS', len(hits))
"""
    result = subprocess.run([sys.executable, "-c", watcher],
                            capture_output=True, text=True,
                            cwd=str(ROOT), timeout=180)
    reported = [line for line in result.stdout.splitlines()
                if line.startswith("CONNECTS")]
    if not reported:
        return -1, result.stdout[-800:]
    return int(reported[-1].split()[1]), result.stdout[-800:]
