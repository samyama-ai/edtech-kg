"""The reporting path, checked as a class rather than one line at a time.

A lint fix once removed an `f` prefix from the wrong string and the probe
printed a literal `{ONET_CROSSWALKS}` to whoever ran it. Nothing caught it:
the print block was exercised by several tests, but every one of them passed
`quiet=True` or asserted on a line the mutation did not touch.

That is the shape of the whole class. A defect on the reporting path is
invisible to every assertion and visible to every user, so it is checked here
against the source rather than against any one run's output.

The first version of this scanned lines and skipped any that did not start
with `print(` — so a continuation line of an implicitly-concatenated print was
never examined, and those are exactly where the placeholders live. It reported
clean while `f"…{a}" "…{b}"` printed the braces of `b`. It is tokenised now:
a `print` call's own string tokens, whatever line each one sits on.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = sorted((ROOT / "etl").rglob("*.py"))

# A brace pair that is not doubled. Doubling is how both a plain string and an
# f-string say "print a literal brace", so `{{KG_SLUG}}` in the cookiecutter
# loader is intentional and reads as clean here without an exemption listing
# it by name — an exemption naming a file goes stale the moment it moves.


def carries_a_placeholder(literal: str) -> bool:
    stripped = literal.replace("{{", "").replace("}}", "")
    opened = stripped.find("{")
    return opened != -1 and stripped.find("}", opened) != -1


def prefix_of(token: str) -> str:
    body = token.lstrip("rRbBuUfF")
    return token[: len(token) - len(body)].lower()


def unprefixed_placeholders(path: Path) -> list[str]:
    """Every string inside a `print(...)` that carries a placeholder and is
    not an f-string — which is to say, will print its own braces."""
    source = path.read_text(encoding="utf-8")
    calls = [(node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
             for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)
             and node.func.id == "print"]

    found = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.STRING:
            continue
        start = token.start
        inside = any((sl, sc) <= start < (el, ec)
                     for sl, sc, el, ec in calls)
        if not inside or "f" in prefix_of(token.string):
            continue
        if carries_a_placeholder(token.string):
            where = path.name if ROOT not in path.parents \
                else path.relative_to(ROOT)
            found.append(f"{where}:{start[0]}: {token.string[:70]}")
    return found


def test_the_modules_are_actually_being_scanned():
    """A scanner over an empty list is a green test that checks nothing —
    the failure mode this file's own predecessor had."""
    assert len(MODULES) >= 10, MODULES
    assert any(p.name.startswith("probe_") for p in MODULES)


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_no_print_carries_a_placeholder_without_an_f_prefix(module):
    offenders = unprefixed_placeholders(module)
    assert not offenders, (
        f"these strings sit inside a print and carry a placeholder without an "
        f"f prefix, so they will print the braces to whoever runs the "
        f"module: {offenders}")


def test_the_scanner_sees_a_placeholder_on_a_continuation_line(tmp_path):
    """The blind spot the line-scanning version had, pinned as a test rather
    than as a claim in a docstring."""
    module = tmp_path / "probe_example.py"
    module.write_text('print(f"a {x}"\n      "   b {y}")\n', encoding="utf-8")
    assert [o.split(": ", 1)[1] for o in unprefixed_placeholders(module)] \
        == ['"   b {y}"']


def test_a_doubled_brace_is_not_a_placeholder(tmp_path):
    """`{{KG_SLUG}}` is a template placeholder the loader means to print."""
    module = tmp_path / "probe_example.py"
    module.write_text('print("loading {{KG_SLUG}} now")\n', encoding="utf-8")
    assert unprefixed_placeholders(module) == []


def test_a_placeholder_outside_a_print_is_not_reported(tmp_path):
    """Only the reporting path. A format string handed to `raise` or `join`
    is read by code that will interpolate it."""
    module = tmp_path / "probe_example.py"
    module.write_text('TEMPLATE = "{name} was not found"\n', encoding="utf-8")
    assert unprefixed_placeholders(module) == []
