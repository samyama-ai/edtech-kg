"""Whether `pip install .` produces something that works.

Split out of `tests/test_repo_layout.py` when it passed the 500-line review
limit. Everything here is about the package: is the metadata buildable, does
`dependencies` describe what the code imports, and does the install ship the
modules the README tells a reader to run.

The failures this catches are all the same shape — an install that SUCCEEDS
and then fails at import or at `python -m`, which reads as a broken repo rather
than a broken package.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tomllib
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def configured_packages() -> list[str]:
    """`include` from pyproject, read at CALL time.

    Read at import it made a malformed or absent `pyproject.toml` a COLLECTION
    error — the whole suite fails to start, and the message is a KeyError from
    a test module rather than the packaging failure it is. Read here, one test
    fails and says what is wrong with the file.
    """
    import tomllib

    return tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["tool"]["setuptools"]["packages"]["find"]["include"]


#: Distribution name -> import name, where they differ. Compared as-is
#: otherwise, which is right for the large majority; a package added later
#: whose names differ shows up as a readable false "declared but imported by
#: nothing" rather than a silent pass.
ALIASES = {"pyyaml": "yaml", "beautifulsoup4": "bs4",
           "python-dateutil": "dateutil", "pillow": "pil"}


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return [n for n in out.stdout.split("\0") if n]


def test_the_package_metadata_is_valid_enough_to_install():
    """`pip install -e .` failed outright: `project.name` must be a PEP 508
    identifier and `{{KG_SLUG}}-kg` is not one, so setuptools rejected the file
    before reading anything else.

    Built rather than pattern-matched, because the ways a pyproject can be
    invalid are not enumerable and the failure guarded against was a category
    error in one field.

    IN-PROCESS, not `pip install --dry-run`: even with `--no-deps` an editable
    install uses build isolation and reaches the index for the backend, so the
    test failed on an offline runner for a reason unrelated to the metadata —
    and CI is such a runner.
    """
    from setuptools import build_meta

    with tempfile.TemporaryDirectory() as out:
        # `os.chdir` is process-global and the only way to point the build
        # backend at a directory — it takes no path argument. The restore is
        # in a `finally` or a raise leaves the whole suite pointed elsewhere.
        # NOT safe under `pytest-xdist`, where a worker runs its own tests in
        # one process; nothing passes `-n` today, and the fix would be a
        # subprocess rather than a lock.
        cwd = os.getcwd()
        os.chdir(ROOT)
        try:
            written = build_meta.prepare_metadata_for_build_wheel(out)
        except Exception as exc:  # noqa: BLE001 - the category is the point
            raise AssertionError(
                f"the packaging metadata does not build, so `pip install -e .` "
                f"cannot work — the README tells readers to run it as step "
                f"two: {type(exc).__name__}: {exc}") from exc
        finally:
            os.chdir(cwd)

        metadata = (Path(out) / written / "METADATA").read_text(errors="replace")

    name = next((line.split(":", 1)[1].strip() for line in metadata.splitlines()
                 if line.lower().startswith("name:")), None)
    assert name == "edtech-kg", (
        f"the built metadata names this package {name!r}. `project.name` must "
        f"be a PEP 508 identifier — the template's brace-wrapped slug was not, "
        f"and setuptools rejected the file before reading anything else.")


def _directory_for(extra: str) -> str:
    """The top-level package an optional extra exists for.

    `[mcp]` is the dependency group for `mcp_server/`. The mapping is by
    convention and stated here rather than guessed at with a `startswith`,
    which would have made `[m]` cover every directory beginning with an m.
    """
    return {"mcp": "mcp_server"}.get(extra, extra)


def _package_name(requirement: str) -> str:
    """The package a PEP 508 requirement names.

    `tomllib` gives the entries whole, so there is no splitting on `,` — which
    was the bug: an ordinary range pin like `x>=1,<3` was cut in half and the
    fragment `<3` failed with "cannot read a package name". The extras parser
    had the same split and silently dropped the fragment instead, so one TOML
    shape was handled two different ways in one file.
    """
    found = re.match(r"[A-Za-z0-9_.-]+", requirement.strip())
    if not found:
        raise AssertionError(
            f"cannot read a package name from the requirement {requirement!r}")
    return found.group(0).lower()


def test_the_declared_dependencies_are_ones_something_imports():
    """The template declared `samyama`, `requests`, `rich`, `click` and
    `fastmcp`. Nothing imported any of them: `click` came from a placeholder
    loader and `fastmcp` from a placeholder MCP server.

    A dependency list nobody needs is its own false claim and makes the install
    heavier than the code. Optional extras are exempt: `mcp` names `fastmcp`
    deliberately, for a server documented as not yet built.

    Both directions are asserted and the second has the teeth: with
    `dependencies = []`, `declared - imported` is empty by construction — the
    vacuous pass CONTRIBUTING.md names — while the converse cannot go vacuous.
    Names go through `ALIASES`, since `PyYAML` imports as `yaml`.
    """
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    declared = {_package_name(entry)
                for entry in project.get("dependencies", [])}

    # Parsed, not pattern-matched. The line regex also matched English — a
    # docstring reading "import the catalogue first" put `the` in the set —
    # invisible while the set was only subtracted FROM, and six phantom
    # dependencies the moment it was used the other way.
    # RUNTIME and TEST imports kept apart. One set meant `pytest` counted as
    # something the package needs to RUN, so it had to be excused by the
    # extras exemption — which then excused a runtime import too: `import
    # requests` in an `etl` module plus `requests` in dev passed, the exact
    # install-succeeds-then-import-fails case this exists to prevent.
    imported, test_only = set(), set()
    # WHERE each import was written, not only that it was. An extra excuses an
    # import inside the package that extra exists for and nowhere else.
    imported_in: dict[str, set[str]] = {}
    for name in tracked():
        if not name.endswith(".py"):
            continue
        try:
            tree = ast.parse((ROOT / name).read_text(errors="replace"))
        except SyntaxError:
            continue
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0].lower() for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0].lower())
        if name.startswith("tests/") or name == "conftest.py":
            test_only |= found
        else:
            imported |= found
            imported_in[name] = found

    # Through the alias map, so `PyYAML` in pyproject and `import yaml` in
    # the code are one package rather than two separate complaints.
    seen = imported | test_only
    unused = {d for d in declared if ALIASES.get(d, d) not in seen}
    assert not unused, (
        f"declared but imported by nothing: {sorted(unused)}. Move it to an "
        f"optional extra or drop it.")

    # The direction that stays meaningful when the list is empty.
    first_party = {d.name for d in ROOT.iterdir() if (d / "__init__.py").exists()}
    first_party |= {p.stem for p in ROOT.glob("*.py")} | {"__future__"}
    # Scoped to the optional-dependencies TABLE, not to everything after its
    # heading. Splitting on the heading and reading to the end of the file
    # swept in every later array — `[tool.setuptools.packages.find]`'s
    # `include`, and anything added below it — so an unrelated entry silently
    # counted as a declared extra and excused an undeclared import.
    extras, dev_only, by_extra = set(), set(), {}
    for group, entries in project.get("optional-dependencies", {}).items():
        for item in entries:
            package = _package_name(item)
            extras.add(package)
            by_extra.setdefault(group, set()).add(package)
            if group == "dev":
                dev_only.add(package)

    stdlib = set(sys.stdlib_module_names)
    # Runtime modules get `dependencies` and the extras, and NOT the dev
    # group: a package that installs without `[dev]` must still import.
    undeclared = sorted(
        # SCOPED to where the import was written. An extra excuses an import
        # only inside the directory that extra exists for — `[mcp]` covers
        # `mcp_server/`, not `etl/`. Subtracting every extra from every module
        # let an unconditional `import fastmcp` in an `etl` module pass, which
        # is exactly the install-succeeds-then-fails-on-import case named
        # above.
        #
        # `dev` excuses nothing here: a package that installs without `[dev]`
        # must still import. And a package in `dev` AND another group is not
        # removed by a subtraction and then punished for being in two lists —
        # the groups are read individually rather than differenced.
        {module
         for name, found in imported_in.items() for module in found
         if module not in stdlib and module not in first_party
         and ALIASES.get(module, module) not in {ALIASES.get(d, d) for d in declared}
         and ALIASES.get(module, module) not in {
             ALIASES.get(d, d)
             for group, names in by_extra.items()
             if group != "dev" and name.split("/")[0] == _directory_for(group)
             for d in names}})
    assert not undeclared, (
        f"imported but declared nowhere: {undeclared}. An install that "
        f"succeeds and then fails on import is worse than one that refuses.")

    # Tests may reach for a dev extra as well, and for nothing else.
    undeclared_in_tests = sorted(
        test_only - stdlib - first_party
        - {ALIASES.get(d, d) for d in declared}
        - {ALIASES.get(d, d) for d in extras})
    assert not undeclared_in_tests, (
        f"the tests import {undeclared_in_tests}, declared nowhere. A "
        f"contributor following CONTRIBUTING.md installs `[dev]` and the "
        f"suite fails to collect.")


def test_every_module_the_readme_tells_you_to_run_is_packaged():
    """`include` listed `etl*` and `mcp_server*` and not `demo*`.

    So `pip install -e .` shipped the MCP stub and left out the demo, which is
    the thing this repo exists to show. `README.md` says to install and run
    `python -m demo.demo`, and from
    outside the repo root that raised `ModuleNotFoundError`. From inside it the
    working directory hides the omission, which is why nothing caught it.

    Derived from the README rather than a list here, so a `python -m` line
    added later is covered the day it is added.
    """
    import setuptools

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    invoked = {match.split(".")[0]
               for match in re.findall(r"python -m ([a-z_][a-z0-9_.]*)", readme)}
    assert invoked, "no `python -m` line found in the README to check"

    packaged = set(setuptools.find_packages(
        where=str(ROOT), include=configured_packages()))

    missing = sorted(name for name in invoked
                     if (ROOT / name / "__init__.py").is_file()
                     and name not in packaged)
    assert not missing, (
        f"the README tells a reader to run {missing} after installing, and "
        f"`pip install .` does not ship them — from any directory other than "
        f"the repo root that is a ModuleNotFoundError. Add them to "
        f"`[tool.setuptools.packages.find] include`.")


def _fake_project(tmp_path, monkeypatch, files: dict, toml: str):
    (tmp_path / "pyproject.toml").write_text(toml, encoding="utf-8")
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body, encoding="utf-8")
        (tmp_path / name).parent.joinpath("__init__.py").touch()
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "tracked", lambda: list(files))


TOML = """[project]
name = "edtech-kg"
dependencies = []
[project.optional-dependencies]
mcp = ["fastmcp"]
dev = ["pytest"]
"""


def test_an_extra_does_not_excuse_an_import_outside_its_own_package(
        tmp_path, monkeypatch):
    """The survivor in this file, and it has teeth.

    Every extra was subtracted from every module, so an unconditional
    `import fastmcp` in an `etl` module passed — `pip install edtech-kg`
    without `[mcp]`, then `import etl.engine`, which is precisely the
    install-succeeds-then-fails-on-import case this file exists to prevent.
    """
    _fake_project(tmp_path, monkeypatch,
                  {"etl/engine.py": "import fastmcp\n"}, TOML)
    with pytest.raises(AssertionError, match="fastmcp"):
        test_the_declared_dependencies_are_ones_something_imports()


def test_an_extra_does_excuse_an_import_inside_its_own_package(
        tmp_path, monkeypatch):
    """The other direction. `[mcp]` names `fastmcp` deliberately, for a server
    that is allowed to need it — a guard that refused this would be wrong."""
    _fake_project(tmp_path, monkeypatch,
                  {"mcp_server/server.py": "import fastmcp\n"}, TOML)
    test_the_declared_dependencies_are_ones_something_imports()


def test_the_extra_is_matched_to_its_directory_by_name_not_by_luck(
        tmp_path, monkeypatch):
    """`[mcp]` is the group for `mcp_server/`, and the names differ.

    Dropping the mapping and comparing the group to the directory directly
    makes `mcp_server/` unmatched, so the deliberate `fastmcp` import starts
    failing — a guard that cries wolf on correct code is one that gets
    switched off.
    """
    assert _directory_for("mcp") == "mcp_server"
    assert _directory_for("dev") == "dev"
    _fake_project(tmp_path, monkeypatch,
                  {"mcp_server/server.py": "import fastmcp\n"}, TOML)
    test_the_declared_dependencies_are_ones_something_imports()


def test_a_range_pin_is_read_as_one_package(tmp_path, monkeypatch):
    """`x>=1,<3` was split on the comma, so `<3` reached the name parser.

    One list raised "cannot read a package name" and the other silently
    dropped the fragment — the same TOML shape handled two ways in one file.
    """
    assert _package_name("packaging>=21,<25") == "packaging"
    assert _package_name('  "PyYAML >= 6, < 7"  '.strip().strip('"')) == "pyyaml"

