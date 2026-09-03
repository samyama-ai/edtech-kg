r"""No module may carry an invalid escape sequence.

Two did, and the suite reported them on every single run — `\|` in
`tests/schema_properties.py` and `\d` in `tests/test_contributing.py`, both
regex text inside a docstring that was not raw. Neither changed a result, which
is exactly why they survived: a warning nobody acts on is noise, and noise is
where a real warning hides.

They are not permanently harmless. Python has escalated this twice — a
DeprecationWarning, then a SyntaxWarning in 3.12 — and the stated direction is
a SyntaxError. A docstring is compiled like any other string, so the day that
lands, two files stop importing and the whole suite stops collecting.

This file is the ratchet. It is deliberately a compile-time check over the
source rather than a `-W error` flag in `pyproject.toml`: the flag would fail
the suite on any third-party warning too, which is how a strict setting gets
switched off six months later.
"""

import pathlib
import warnings

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The directories this repo owns. A vendored or generated tree would be listed
#: here as an exclusion with a reason, rather than the walk being narrowed
#: silently until it covers nothing.
OURS = ("etl", "tests", "demo", "mcp_server", "benchmarks")


def modules() -> list[pathlib.Path]:
    return sorted(path for directory in OURS
                  for path in (ROOT / directory).rglob("*.py")
                  if "__pycache__" not in path.parts)


def test_the_walk_finds_the_modules_it_claims_to_check():
    """The vacuous-parse guard. A rename of `etl/` would leave every assertion
    below iterating an empty list and passing, which is indistinguishable from
    a clean tree."""
    found = modules()
    assert len(found) > 50, (
        f"only {len(found)} modules found — the walk is broken")
    names = {path.name for path in found}
    missing = {"engine.py", "load_pwcs.py", "probe_pwcs.py"} - names
    assert not missing, f"the walk missed {sorted(missing)}"


def test_no_module_carries_an_invalid_escape_sequence():
    r"""Compile every module and collect what Python says about it.

    `compile()` is used rather than `import` because importing runs the module,
    and a module that reaches the network or an engine on import would make
    this test do the same. The warning is raised at compile time, so compiling
    is enough.
    """
    offenders = []
    for path in modules():
        source = path.read_text(encoding="utf-8")
        with warnings.catch_warnings(record=True) as raised:
            warnings.simplefilter("always")
            try:
                compile(source, str(path), "exec")
            except SyntaxError as broken:
                offenders.append(f"{path.relative_to(ROOT)}: {broken}")
                continue
            offenders += [
                f"{path.relative_to(ROOT)}:{w.lineno} {w.message}"
                for w in raised if "escape sequence" in str(w.message)]

    assert not offenders, (
        "invalid escape sequences — prefix the string with `r`:\n  "
        + "\n  ".join(offenders)
        + "\nThese are warnings today and a SyntaxError in a future Python, "
          "at which point the module stops importing.")
