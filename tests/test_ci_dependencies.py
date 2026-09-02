"""What CI installs, against what the suite actually needs.

Split from `tests/test_ci_workflow.py` when it passed the 500-line review
limit. Split by SUBJECT: that file asserts the workflow's own guarantees — it
runs on a PR, it starts an engine, an unexpected skip fails the run. This one
asks a single different question: does the install step cover everything the
suite reaches for?

Two ways to reach for something, and only one used to be read. An import walk
cannot see `subprocess.run([sys.executable, "-m", "flake8", …])`, so a
dependency reached that way was invisible to the guard while being exactly
what it exists to catch — and a test in this repo did that while CI installed
only pytest, passing locally because the developer had flake8.
"""

from __future__ import annotations

import ast
import re
import sys
import pytest

from tests.test_ci_workflow import ROOT, WORKFLOW


# DEFINED here rather than imported. An imported fixture binds a module global
# that every test taking it then shadows, which pyflakes reads as a
# redefinition and a reader reads as a puzzle — and `test_registry_probe.py`
# already carries the same note for the same reason. Three lines is cheaper
# than the coupling.
@pytest.fixture(scope="module")
def workflow() -> str:
    if not WORKFLOW.exists():
        pytest.fail(f"{WORKFLOW.relative_to(ROOT)} is missing — "
                    f"the suite gates nothing (#18)")
    return WORKFLOW.read_text(encoding="utf-8")


def packages_installed(workflow: str) -> set[str]:
    """What the workflow's `run:` commands actually install.

    Anchored to the `run:` COMMAND, not to any line mentioning `pip install`.
    Both YAML spellings — `run:` on its own line and `- run:` as the first key
    of a step — because the second is equally valid and was invisible to this
    guard, which would have read a workflow that installs everything as one
    that installs nothing.
    `ci.yml` discusses `pip install -e .` and `pip install --dry-run` in the
    comment block above the step, so matching the phrase anywhere absorbed
    English from those comments — `and`, `but`, `deliberate`, `is`, `not`,
    `still`, `that` — and the guard could then be satisfied by a word in prose
    rather than by a package in the install step. A vacuous pass in the check
    written to close one.

    A named function because the test below drives THIS, not a copy of it. The
    first version of that test re-implemented the regex inline, so reverting
    this one left it green — it was verifying a duplicate parser.
    """
    found = set()
    # BLOCK scalars too. `run: |` puts the commands on the following lines,
    # indented, and a single-line regex sees none of them — so folding the
    # install step into a block, which `ci.yml` already does for three of its
    # five steps, would silently yield an empty install set and the guard
    # would report a workflow that installs everything as one that installs
    # nothing.
    commands = []
    lines = workflow.splitlines()
    for i, line in enumerate(lines):
        head = re.match(r"^(\s*)-?\s*run:\s*(\|-?|>-?)?\s*(.*)$", line)
        if not head:
            continue
        indent, block, inline = head.group(1), head.group(2), head.group(3)
        if block:
            for follow in lines[i + 1:]:
                if follow.strip() and not follow.startswith(indent + " "):
                    break
                commands.append(follow)
        elif inline:
            commands.append(inline)

    # Join backslash continuations, so `pip install \` followed by the
    # packages on the next line is one command rather than two halves, the
    # second of which mentions no `pip install` and is therefore ignored.
    joined, buffer = [], ""
    for command in commands:
        buffer += command.rstrip()[:-1] + " " if command.rstrip().endswith("\\") else command
        if not command.rstrip().endswith("\\"):
            joined.append(buffer)
            buffer = ""
    if buffer:
        joined.append(buffer)
    commands = joined

    for raw in commands:
        # COMMENTS ARE NOT COMMANDS, and this is the dangerous direction. A
        # `#` line inside a `run: |` block was read as an install — measured,
        # `# pip install evil` put `evil` in the installed set — and an inline
        # `# and flake8` contributed `#`, `and` and `flake8`. Both INFLATE
        # what CI is believed to install, so the guard reports a dependency as
        # covered when the install step never mentions it. That is a false
        # green in the check written to prevent one.
        command = raw.split("#", 1)[0]
        # A trailing backslash continues the command onto the next line, and
        # splitting per line dropped everything after it.
        if command.rstrip().endswith("\\"):
            command = command.rstrip()[:-1]
        for piece in re.findall(r"pip install([^\n;&|]*)", command):
            skip_next = False
            for word in piece.split():
                if skip_next:
                    # The VALUE of the flag before it. `-r requirements.txt`
                    # put the filename in as a package and `--index-url
                    # https://x` put the URL in; neither is something pip
                    # installs by that name.
                    skip_next = False
                    continue
                if word.startswith("-"):
                    skip_next = word in ("-r", "-c", "--index-url",
                                         "--extra-index-url", "--find-links")
                    continue
                if word == ".":
                    # `pip install -e .` installs THIS package, not one named
                    # `.` — and it is the thing the workflow deliberately does
                    # not do, so counting it made the set say otherwise.
                    continue
                # Quotes stripped first. A pinned dependency is normally
                # quoted in a shell command — `"setuptools>=61.0"` — and
                # leaving the quote on made the token `"setuptools`, which
                # matches nothing, so the guard reported a package as missing
                # that the same line installs.
                # `~` and `;` too. PEP 508 spells a compatible-release pin
                # `packaging~=24.0`, which split to `packaging~` — a name no
                # install line contains, so the guard would report the package
                # as missing while it is right there. `;` starts an
                # environment marker.
                found.add(re.split(r"[<>=!~;\[]", word.strip('"\''))[0].lower())

    return found


def modules_run_as_subprocesses(tree: ast.AST) -> set[str]:
    """Modules invoked as `[sys.executable, "-m", "<name>", ...]`.

    A dependency reached this way is INVISIBLE to an import walk, so the guard
    below could not see it by construction. That is not hypothetical: a test in
    this repo shelled out to `python -m flake8` while CI installed only pytest,
    and it passed locally because the developer's environment happened to have
    flake8. The guard written to prevent exactly that could not report it.

    Matched on the pair rather than on `-m` alone: `sys.executable` followed by
    `-m` followed by a literal name. A computed module name is not matched, and
    is not something to guess at.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue
        parts = [e.value if isinstance(e, ast.Constant) else e
                 for e in node.elts]
        for index, part in enumerate(parts[:-2]):
            # `sys.executable`, or the interpreter spelled out. A workflow
            # that hardcodes `python3` is the likelier of the two in a shell
            # script and was walking straight through.
            executable = (
                (isinstance(part, ast.Attribute)
                 and part.attr == "executable"
                 and isinstance(part.value, ast.Name)
                 and part.value.id == "sys")
                or (isinstance(part, str)
                    # `/usr/bin/python3` as readily as `python3` — a script
                    # that spells the path out is running the same thing.
                    and re.fullmatch(r"(?:/[\w./-]*/)?python(?:3(?:\.\d+)?)?",
                                     part)))
            if executable and parts[index + 1] == "-m" \
                    and isinstance(parts[index + 2], str):
                found.add(parts[index + 2].split(".")[0])
    return found

#: Shipped with the interpreter or with pip itself. `python -m pip install …`
#: is not a dependency: the suite does not import it, and `pip` is not a thing
#: you add to a `pip install` line — the message was wrong twice over.
#: `test_packaging.py` discusses the `pip install --dry-run` route it chose not
#: to take, so this is the next shape someone reaches for.


BOOTSTRAP = {"pip", "setuptools", "wheel", "venv", "ensurepip"}


def dependencies_of(paths, root):
    """What these modules IMPORT and what they RUN, as two sets.

    Extracted so the wiring can be driven. The subprocess walk was added to
    the guard and nothing asserted the guard CONSUMED it — deleting that one
    line left the whole suite green, which is the same defect one layer out
    from the one it was written to fix.
    """
    imported: set[str] = set()
    run: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            imported.update(n.split(".")[0] for n in names)
        run |= modules_run_as_subprocesses(tree)

    # First-party names are read from the tree rather than listed. A hand-kept
    # list means a test importing `mcp_server` or `schema` is reported as an
    # uninstalled dependency, pointing at the install step rather than the
    # import.
    first_party = {d.name for d in root.iterdir() if (d / "__init__.py").exists()}
    first_party |= {p.stem for p in root.glob("*.py")} | {"__future__"}
    ours = set(sys.stdlib_module_names) | first_party
    # BOOTSTRAP applies to what is RUN, not to what is imported. Subtracted
    # from both, `import setuptools` in a test was hidden — and that IS a
    # dependency, however usually present. `python -m pip` is not.
    return imported - ours, run - ours - BOOTSTRAP


def test_the_workflow_installs_what_the_suite_actually_imports(workflow):
    """The suite needs pytest and the standard library, measured — so that is
    what CI installs.

    `pip install -e .` is not used, and the reason changed with this branch.
    It used to be that the packaging was broken — the template's placeholder
    name is not a valid identifier, so the install failed before it started.
    #17 fixed that, and this file is part of #17, so the old reason was an
    argument for a state the same branch removes. It survived here after being
    corrected in `ci.yml`, which is the sweep this round is about.

    The reason now is that installing adds nothing and costs something:
    `dependencies` is empty because outside the standard library this package
    imports nothing, while build isolation would reach the index for a
    backend.

    Scoped to the modules the suite REACHES — the tests, this conftest, and the
    `etl` modules the tests import. Not every file in the tree: a module the
    suite never imports can carry a third-party import that CI never executes,
    and compiling it here would fail for a reason CI does not have.

    The scope is DERIVED below by walking the imports, never listed here. A
    docstring that names the files it excludes is wrong the moment one of them
    is renamed or deleted, and it is wrong silently — the test keeps passing
    and the paragraph keeps explaining a tree that no longer exists.
    """
    # Through `packages_installed`, not a second unanchored regex. This line
    # is the pattern that helper exists to replace: `pip install[^\n]*pytest`
    # matches the phrase anywhere, including the comment block above the step
    # that discusses `pip install -e .` — so the check the whole file is about
    # was still being made the old way, three lines from the fix.
    assert "pytest" in packages_installed(workflow), "pytest is not installed"

    reached = set(ROOT.glob("tests/**/*.py")) | {ROOT / "conftest.py"}
    for path in sorted(reached):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("etl."):
                candidate = ROOT / (node.module.replace(".", "/") + ".py")
                if candidate.exists():
                    reached.add(candidate)

    imported, run = dependencies_of(sorted(reached), root=ROOT)

    # What CI installs is READ from the workflow, not listed here. A literal
    # `{"pytest"}` meant adding a package to the install step left this test
    # still failing, and adding an import left it still passing — the drift
    # this file exists to catch, in the assertion that catches it.
    installed = packages_installed(workflow)
    missing_imports = {n for n in imported if n.lower() not in installed}
    missing_runs = {n for n in run if n.lower() not in installed}

    # Reported SEPARATELY, because they are different facts and one was being
    # described wrongly: a module the suite RUNS as a subprocess is not one it
    # imports, and telling someone their suite imports `flake8` sends them
    # looking for an import that is not there.
    assert not (missing_imports or missing_runs), (
        (f"the suite imports {sorted(missing_imports)}. " if missing_imports else "")
        + (f"the suite RUNS `python -m` on {sorted(missing_runs)}. "
           if missing_runs else "")
        + f"CI installs {sorted(installed)}. Either add it to the install step "
          f"or drop the dependency.")


def test_a_module_run_as_a_subprocess_is_seen_as_a_dependency():
    """The case the import walk could not see. `python -m flake8` in a test,
    against a CI that installs only pytest, is an install-succeeds-then-fails
    shape — and it passed locally because the developer had flake8."""
    tree = ast.parse(
        'import subprocess, sys\n'
        'subprocess.run([sys.executable, "-m", "flake8", "--select=E302", "x.py"])\n')
    assert modules_run_as_subprocesses(tree) == {"flake8"}


def test_the_module_name_is_taken_from_the_position_after_dash_m():
    """Not from "any string near a -m". The invocation's shape is what makes
    the name a module name."""
    tree = ast.parse(
        'import sys\n'
        'run([sys.executable, "-m", "pytest", "-q", "-m", "slow"])\n')
    # `slow` is a MARKER argument to `-m`, not a module: only the name
    # directly after `sys.executable, "-m"` is one.
    assert modules_run_as_subprocesses(tree) == {"pytest"}


def test_another_executable_is_not_read_as_a_python_module():
    """`git`, `docker` and the rest are not pip-installable, and reporting one
    as a missing dependency would send a reader to the wrong step."""
    tree = ast.parse('run(["git", "-m", "something"])\n'
                     'run(["docker", "run", "-m", "512m", "image"])\n')
    assert modules_run_as_subprocesses(tree) == set()


def test_a_computed_module_name_is_not_guessed_at():
    """A name built at runtime is not something to report as uninstalled."""
    tree = ast.parse('import sys\nrun([sys.executable, "-m", name])\n')
    assert modules_run_as_subprocesses(tree) == set()


def test_a_subprocess_dependency_reaches_the_guard(tmp_path):
    """Drives `dependencies_of`, which is what the guard calls. Deleting the
    `run |= modules_run_as_subprocesses(...)` line fails this."""
    (tmp_path / "tests").mkdir()
    module = tmp_path / "tests" / "test_thing.py"
    module.write_text(
        "import subprocess, sys\n"
        'subprocess.run([sys.executable, "-m", "flake8", "x.py"])\n',
        encoding="utf-8")
    imported, run = dependencies_of([module], root=tmp_path)
    assert run == {"flake8"}, "the subprocess walk is not wired into the guard"
    assert "flake8" not in imported, "a run dependency is not an import"


def test_an_import_and_a_run_are_reported_apart(tmp_path):
    """They are different facts, and the message said the wrong one. Telling
    someone their suite IMPORTS flake8 sends them looking for an import that
    is not there."""
    (tmp_path / "tests").mkdir()
    module = tmp_path / "tests" / "test_thing.py"
    module.write_text(
        "import subprocess, sys\n"
        "import pytest\n"
        'subprocess.run([sys.executable, "-m", "flake8"])\n',
        encoding="utf-8")
    imported, run = dependencies_of([module], root=tmp_path)
    assert imported == {"pytest"} and run == {"flake8"}


def test_running_python_m_pip_is_not_a_dependency(tmp_path):
    """`pip` is not something you add to a `pip install` line, and the suite
    does not import it. Reported as one, the message was wrong twice over."""
    (tmp_path / "tests").mkdir()
    module = tmp_path / "tests" / "test_thing.py"
    module.write_text(
        "import subprocess, sys\n"
        'subprocess.run([sys.executable, "-m", "pip", "install", "x"])\n',
        encoding="utf-8")
    _, run = dependencies_of([module], root=tmp_path)
    assert run == set(), f"pip reported as a dependency: {run}"


def test_a_hardcoded_interpreter_is_still_a_subprocess_dependency():
    """`["python3", "-m", "flake8"]` is the likelier spelling in a script and
    was walking straight through."""
    for interpreter in ("python", "python3", "python3.11"):
        tree = ast.parse(f'run(["{interpreter}", "-m", "flake8"])\n')
        assert modules_run_as_subprocesses(tree) == {"flake8"}, interpreter


def test_a_tuple_argument_is_read_like_a_list():
    """`subprocess.run` takes either, and only one was read."""
    tree = ast.parse('import sys\nrun((sys.executable, "-m", "flake8"))\n')
    assert modules_run_as_subprocesses(tree) == {"flake8"}


def test_a_dotted_module_is_reported_by_its_package(tmp_path):
    """`python -m pytest.__main__` is pytest, and the install line names the
    package rather than the module path."""
    tree = ast.parse('import sys\nrun([sys.executable, "-m", "flake8.main"])\n')
    assert modules_run_as_subprocesses(tree) == {"flake8"}


# --------------------------------------------------------------------------
# THE SEAM, driven end to end.
#
# Three rounds running, the fix moved this shape rather than removed it: the
# parser got covered, then `dependencies_of` got covered, and each time the
# join to the thing that ASSERTS stayed untested. Covering another unit would
# move it a fourth time.
#
# So this drives the guard itself — the real function, a fabricated tree, a
# fabricated workflow — and asserts on the message a reader would get. There
# is no seam left between input and assertion because the whole path runs.
# --------------------------------------------------------------------------

def _tree(tmp_path, body: str):
    """A repo-shaped tree the guard can walk."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_thing.py").write_text(body, encoding="utf-8")
    (tmp_path / "conftest.py").write_text("", encoding="utf-8")
    return tmp_path


INSTALLS_PYTEST_ONLY = (
    "jobs:\n  test:\n    steps:\n"
    '      - run: python -m pip install --quiet pytest "setuptools>=61.0"\n')


def test_the_guard_reports_a_module_the_suite_only_RUNS(tmp_path, monkeypatch):
    """The blocker, driven at the seam. Deleting the `missing_runs` line — or
    dropping `run` from `dependencies_of` — fails here."""
    monkeypatch.setattr(sys.modules[__name__], "ROOT",
                        _tree(tmp_path, 'import subprocess, sys\n'
                                        'subprocess.run([sys.executable, "-m", "flake8"])\n'))
    with pytest.raises(AssertionError) as raised:
        test_the_workflow_installs_what_the_suite_actually_imports(INSTALLS_PYTEST_ONLY)
    message = str(raised.value)
    assert "flake8" in message, message
    assert "RUNS" in message, (
        f"a run-only dependency was reported as an import, which sends a "
        f"reader looking for an import that is not there: {message}")


def test_the_guard_says_IMPORTS_for_an_import(tmp_path, monkeypatch):
    """The other half of the same message. Reported as a run, it would send a
    reader looking for a subprocess that is not there."""
    monkeypatch.setattr(sys.modules[__name__], "ROOT",
                        _tree(tmp_path, "import requests\n"))
    with pytest.raises(AssertionError) as raised:
        test_the_workflow_installs_what_the_suite_actually_imports(INSTALLS_PYTEST_ONLY)
    message = str(raised.value)
    assert "requests" in message and "imports" in message, message
    assert "RUNS" not in message, message


def test_the_guard_passes_when_the_workflow_covers_both(tmp_path, monkeypatch):
    """Or the two above pass by refusing everything."""
    monkeypatch.setattr(sys.modules[__name__], "ROOT",
                        _tree(tmp_path, 'import subprocess, sys\nimport pytest\n'
                                        'subprocess.run([sys.executable, "-m", "flake8"])\n'))
    test_the_workflow_installs_what_the_suite_actually_imports(
        "jobs:\n  test:\n    steps:\n"
        "      - run: python -m pip install --quiet pytest flake8\n")


def test_an_imported_bootstrap_package_is_not_hidden(tmp_path, monkeypatch):
    """BOOTSTRAP applies to what is RUN. Subtracted from imports too, a test
    doing `import setuptools` was hidden — and that is a dependency, however
    usually present."""
    imported, run = dependencies_of(
        [_tree(tmp_path, "import setuptools\n") / "tests" / "test_thing.py"],
        root=tmp_path)
    assert imported == {"setuptools"}
    assert run == set()


def test_an_absolute_interpreter_path_is_still_an_interpreter():
    """A script spelling the path out runs the same thing."""
    for spelling in ("/usr/bin/python3", "/usr/local/bin/python3.11", "python3"):
        tree = ast.parse(f'run(["{spelling}", "-m", "flake8"])\n')
        assert modules_run_as_subprocesses(tree) == {"flake8"}, spelling
