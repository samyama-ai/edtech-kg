"""The repo as a published artefact — layout, packaging, and no template left in it.

This repo shipped for a week with `name = "{{KG_SLUG}}-kg"` in `pyproject.toml`,
which made `pip install -e .` fail before it started — step two of the README's
own quick start. More files carried template placeholders, `LICENSE` among
them, in a public repo.

None of it was caught because nothing looked at the repo as a thing someone
else installs and reads. These tests do that — edtech-kg#17 and #6.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The layout every `*-kg` repo shares, so that anyone who has seen one can
# navigate this one without being told.
EXPECTED_DIRS = ("etl", "schema", "docs", "benchmarks", "mcp_server", "demo", "tests")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return [n for n in out.stdout.split("\0") if n]


def test_no_tracked_file_still_carries_a_template_placeholder():
    """`{{KG_NAME}}`, `{{KG_SLUG}}`, `{{YEAR}}` — the template's markers.

    Eight files still held one, including `LICENSE`, whose copyright year was
    literally `{{YEAR}}`. Matched as `{{IDENTIFIER}}` rather than as a list of
    the three known names, because the template can add a fourth and the point
    is that no placeholder ships, not that these three do not.

    f-strings produce `{{` legitimately, and the pattern no longer excludes
    them by shape: widening it to Jinja's spaced and lower-case spellings means
    `f"{{literal}}"` matches too. That is a deliberate trade — measured over
    every tracked file, the wider pattern matches exactly what the narrow one
    did, and the four `{{ }}` users in `etl/` all produce `{{{key}: …}}`
    shapes it does not touch. If an f-string escape ever collides, the fix is
    an exemption for that file, not a narrower pattern: a template placeholder
    in a comment ships to a reader and an f-string escape does not.
    """
    # `\s*` and `A-Za-z`, because `{{ KG_NAME }}` is Jinja's CANONICAL
    # spelling and `{{kg_name}}` is ordinary. The narrow upper-case-only form
    # matched neither, so the two spellings a template is most likely to ship
    # walked straight through the guard written to stop them.
    #
    # Widened after measuring: over every tracked file, this matches exactly
    # what the narrow pattern matched and nothing else, so the f-string
    # brace-escape worry the docstring raises is not realised in this tree.
    placeholder = re.compile(r"\{\{\s*[A-Za-z][A-Za-z0-9_]*\s*\}\}")
    found = []
    for name in tracked():
        # THE NAME ITSELF. A template ships `{{KG_SLUG}}_loader.py` as readily
        # as it ships one inside a file, and scanning only contents could not
        # see it.
        if placeholder.search(name):
            found.append(f"{name}: in the FILENAME")
        path = ROOT / name
        if not path.is_file():
            continue
        # `tests/` is exempt, and it is the ONLY exemption. Every legitimate
        # occurrence in this repo is here: this file writes the markers in its
        # own docstrings and fixtures, and `test_packaging.py` quotes the
        # broken `name = "{{KG_SLUG}}-kg"` it exists to have fixed. Measured —
        # 8 occurrences across exactly two files, and nothing else in the tree.
        #
        # A DIRECTORY rather than the two file names: a third test about this
        # guard should not need an edit here to be written, and a two-name
        # list is the kind that rots into exempting something nobody meant.
        if name.startswith("tests/"):
            continue
        # BINARIES skipped. `errors="replace"` means a `.gif` never raises —
        # it decodes to mojibake and gets scanned, which is slow and can only
        # produce a false positive. A NUL byte in the first block is what
        # `git` itself uses.
        try:
            if b"\0" in path.read_bytes()[:8000]:
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for hit in sorted(set(placeholder.findall(body))):
            found.append(f"{name}: {hit}")
    assert not found, (
        f"template placeholders still in the repo: {sorted(found)}. This is a "
        f"public repo; a reader sees them before they see anything else.")


@pytest.mark.parametrize("placement,text", [
    ("a Python comment", "# a {{KG_NAME}} in a comment"),
    ("a Python docstring", '"""A {{KG_NAME}} in a docstring."""'),
    ("a YAML comment", "# build the {{KG_NAME}} image"),
    ("a Cypher // line", "// the {{KG_NAME}} schema"),
    ("a Markdown heading", "# The {{KG_NAME}} Benchmarks"),
    ("a Python value", 'NAME = "{{KG_SLUG}}-kg"'),
    ("a JSON value", '{"name": "{{KG_SLUG}}"}'),
    # Jinja's canonical spacing, and the lower-case form. The narrow pattern
    # required an upper-case identifier with no whitespace, so both shipped.
    ("Jinja's spaced form", "# a {{ KG_NAME }} with spaces"),
    ("a lower-case name", 'NAME = "{{kg_slug}}-kg"'),
])
def test_the_guard_catches_a_placeholder_wherever_it_is_written(
        placement, text, tmp_path, monkeypatch):
    """Nine placements, and the guard used to miss six of them.

    It stripped comments and docstrings before matching, on the argument that
    a placeholder in prose is prose ABOUT the placeholder. That argument does
    not survive contact with what ships: a comment and a docstring are both
    read by anyone browsing the repo or calling `help()`, which is the guard's
    own stated reason for existing.

    Measured against the eight template files this repo actually had:
    `etl/download_data.py` was not reported at all — its only placeholder was
    in a comment — and `mcp_server/server.py` was caught only incidentally,
    because a second one sat in a value. Its module docstring was invisible.

    The parametrised text is written with real braces because this file is
    exempt from the guard; every other file in the tree is not.
    """
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    (tmp_path / "shipped.py").write_text(text, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "tracked", lambda: ["shipped.py"])
    with pytest.raises(AssertionError, match="template placeholders"):
        test_no_tracked_file_still_carries_a_template_placeholder()


def test_a_placeholder_in_a_filename_is_caught(tmp_path, monkeypatch):
    """A template ships `{{KG_SLUG}}_loader.py` as readily as it ships one
    inside a file, and a guard that reads only contents cannot see it."""
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "tracked",
                        lambda: ["etl/{{KG_SLUG}}_loader.py"])
    with pytest.raises(AssertionError, match="in the FILENAME"):
        test_no_tracked_file_still_carries_a_template_placeholder()


def test_only_tests_are_exempt(tmp_path, monkeypatch):
    """The exemption is a directory, and it has to be exactly that directory.

    Widening it to anything containing "test" would exempt `etl/testing.py`;
    dropping it makes this file fail against itself.
    """
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    for name in ("tests/x.py", "etl/testing.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text('N = "{{KG_SLUG}}"', encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "tracked",
                        lambda: ["tests/x.py", "etl/testing.py"])
    with pytest.raises(AssertionError, match="etl/testing.py"):
        test_no_tracked_file_still_carries_a_template_placeholder()


#: Read from `pyproject.toml`, never restated. A second copy of this list is
#: how the packaging test comes to agree with itself rather than with the file
#: that decides what ships.


@pytest.mark.parametrize("name", EXPECTED_DIRS)
def test_the_shared_layout_is_present(name):
    """Same seven directories as every sibling `*-kg` repo."""
    assert (ROOT / name).is_dir(), f"{name}/ is missing from the shared layout"


@pytest.mark.parametrize("name", EXPECTED_DIRS)
def test_no_directory_in_the_layout_is_silently_empty(name):
    """An empty directory reads as "nothing to do here", the opposite of
    what it means. `benchmarks/` and `mcp_server/` hold only a README, and
    each says so and names the issue tracking it.
    """
    entries = [p for p in (ROOT / name).iterdir() if p.name != "__pycache__"]
    assert entries, f"{name}/ is empty — say what lands there, or remove it"


def test_the_short_meeting_set_is_the_same_in_every_place_it_appears():
    """It appears in four files, and a correction reached one of them.

    `demo/demo.py` states it twice, `README.md` once and `demo/README.md`
    once. Adding the missing question to one left three quoting a set that no
    longer exists — the drift this repo keeps finding, in a string a presenter
    copies before a meeting.
    """
    # The GIF is recorded from a DIFFERENT and shorter set, on a line carrying
    # `--auto`. That one is meant to differ, so it is excluded rather than
    # forced to agree — a test that flattens two deliberate sets into one
    # would be demanding a bug.
    quoted = set()
    for name in ("demo/demo.py", "README.md", "demo/README.md"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if "--auto" in line:
                continue
            quoted |= set(re.findall(r"--only ([\d,]+)", line))

    assert quoted, (
        "no `--only` set is quoted anywhere in the repo, so this check read "
        "nothing — it reported 'quoted as []' as though that were a conflict")
    assert len(quoted) == 1, (
        f"the short-meeting set is quoted as {sorted(quoted)} across the repo "
        f"— a presenter copying one of them runs a different demo")


def test_the_short_meeting_set_runs_the_question_its_pitch_depends_on():
    """The pitch is "fail Algebra 1 and courses close off — and they are not
    the subjects anyone expects". The second half is Q16, and the set ran the
    first half and stopped."""
    from demo.demo import QUESTIONS, chosen as parse_only

    text = (ROOT / "demo" / "README.md").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines()
             if "--only" in line and "--auto" not in line]
    assert lines, (
        "demo/README.md no longer shows a non-`--auto` `--only` line, so this "
        "check read nothing — `lines[0]` was an IndexError where a message "
        "belongs")
    quoted = re.findall(r"--only ([\d,]+)", lines[0])
    assert quoted, f"no `--only` numbers on {lines[0]!r}"

    # Parsed by the DEMO'S OWN function, not by indexing QUESTIONS directly.
    # `--only` is 0-based — `chosen()` refuses anything outside
    # `0..len(QUESTIONS)-1` and the CLI help says so — but a test that indexes
    # the list itself is asserting that convention rather than reading it, and
    # would go quietly wrong the day the numbering changed. This way the test
    # and the CLI cannot disagree.
    chosen = parse_only(quoted[0])

    assert 16 in chosen, (
        "Q16 is missing, so the demo makes a claim about subjects and never "
        "shows them")
    assert {QUESTIONS[i]["tier"] for i in chosen} == {1, 2, 3, 4, 5}, (
        "the set no longer reaches every tier, which is what the page claims "
        "of it")


def test_no_module_leaves_a_helper_or_constant_behind():
    """Splitting a file leaves residue, and `pyflakes` cannot see it.

    Unused module-level FUNCTIONS and CONSTANTS are flagged by no linter this
    repo runs. Three splits in three rounds each left something behind,
    invisible to a green suite and a clean style run. `_`-prefixed names and
    `pytest_*` hooks are exempt.
    """
    sources = {name: (ROOT / name).read_text(encoding="utf-8", errors="replace")
               for name in tracked()
               if name.endswith(".py") and not name.endswith("__init__.py")}

    # IMPORT-AWARE. Matching bare names was still too loose: a dead `URL` in
    # `etl/engine.py` is indistinguishable from the live `URL` in another
    # module, and `URL`, `parse` and `population` all walked through because
    # the name exists somewhere. A module-level name is used elsewhere only if
    # another file IMPORTS that module and then names it — as
    # `from etl.engine import URL`, or `import etl.engine as e` then `e.URL`.
    def module_of(path_name: str) -> str:
        return path_name[:-3].replace("/", ".")

    referenced_elsewhere: dict[str, set[str]] = {n: set() for n in sources}
    for other, text in sources.items():
        try:
            other_tree = ast.parse(text)
        except SyntaxError:
            continue
        direct: set[str] = set()          # names pulled in by `from X import n`
        aliases: dict[str, str] = {}      # local alias -> module it refers to
        for node in ast.walk(other_tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    direct.add(alias.asname or alias.name)
                    aliases.setdefault(alias.asname or alias.name, node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        attributes = {n.attr for n in ast.walk(other_tree)
                      if isinstance(n, ast.Attribute)}
        plain = {n.id for n in ast.walk(other_tree) if isinstance(n, ast.Name)}
        # A name reached by string — `monkeypatch.setattr(m, "THING")`, a
        # getattr. Rare, real, and cheap to keep.
        by_string = {n.value for n in ast.walk(other_tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)}

        for target in sources:
            if target == other:
                continue
            module = module_of(target)
            imported = any(m == module or m.startswith(module + ".")
                           or module.startswith(m + ".")
                           for m in aliases.values())
            if not imported:
                continue
            referenced_elsewhere[target] |= (direct & plain) | attributes | by_string

    offenders = []
    for name, body in sources.items():
        try:
            tree = ast.parse(body)
        except SyntaxError:
            continue
        # DECORATED functions are registered by name and called by the
        # framework, never referenced: a `@pytest.fixture` is consumed as a
        # test parameter, and this guard would report every one in the repo as
        # dead. `pytest_*` are hooks, called by name and referenced nowhere.
        decorated = {n.name for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.decorator_list}
        # `AsyncFunctionDef` too — it was collected by neither branch, so an
        # orphaned `async def` was invisible to a guard about orphans.
        defined = {n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef))
                   and not n.name.startswith(("_", "test_", "pytest_"))}
        # Tuple targets as well: `A, B = 1, 2` binds two names and neither was
        # collected, so the multiple-assignment form of the thing this test
        # exists to catch was invisible to it.
        defined |= {t.id for n in tree.body if isinstance(n, ast.Assign)
                    for target in n.targets
                    for t in (target.elts if isinstance(target, (ast.Tuple, ast.List))
                              else [target])
                    if isinstance(t, ast.Name) and not t.id.startswith("_")}
        # `ORPHAN: int = 7` is an AnnAssign, not an Assign, and was collected
        # by neither branch — so the annotated form of the thing this test
        # exists to catch was invisible to it.
        defined |= {n.target.id for n in tree.body
                    if isinstance(n, ast.AnnAssign)
                    and isinstance(n.target, ast.Name)
                    and not n.target.id.startswith("_")}

        # `ast.Load` ONLY. `ast.walk` visits the assignment TARGET as well, so
        # every assigned constant appeared in `used` by construction and the
        # constant half of this test could never fire: `defined` and `used`
        # both held the name, and `dead` was empty for a name nothing reads.
        # Functions were caught because a `def` produces no `ast.Name` at all.
        used = {node.id for node in ast.walk(tree)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
        used |= {node.attr for node in ast.walk(tree)
                 if isinstance(node, ast.Attribute)}
        # REFERENCED, not "appears in the text". A raw substring let a dead
        # constant named `URL`, `parse` or `population` walk through, because
        # those appear in 65, 68 and several other files as parts of other
        # names — measured. Sharpest case: `ORPHAN_LIMIT` survived because that
        # name is in this file's own `parametrize`.
        #
        # Read from parsed ASTs so a mention in a comment, a docstring or a
        # longer identifier is not a use. Built once for the whole tree rather
        # than per file: per name was twelve seconds.
        dead = sorted(n for n in defined - used - decorated
                      if n not in referenced_elsewhere[name])
        if dead:
            offenders.append(f"{name}: {dead}")

    assert not offenders, (
        f"defined and used nowhere — {offenders}. A split leaves these behind "
        f"and no linter this repo runs reports them.")


@pytest.mark.parametrize("orphan", ["ORPHAN_LIMIT = 7", "ORPHAN_LIMIT: int = 9"])
def test_a_constant_nothing_reads_is_caught(orphan, tmp_path, monkeypatch):
    """The half of the guard above that could not fire.

    `ast.walk` visits the assignment TARGET as well as every use, so an
    assigned constant was in `used` by construction and `dead` was empty for a
    name nothing reads. Functions were caught only incidentally — a `def`
    produces no `ast.Name` at all — so the test passed while doing half of
    what its docstring promised.

    Both forms, because the annotated one is an `AnnAssign` and was collected
    by neither branch.
    """
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    (tmp_path / "etl").mkdir()
    (tmp_path / "etl" / "thing.py").write_text(orphan + "\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "tracked", lambda: ["etl/thing.py"])
    with pytest.raises(AssertionError, match="ORPHAN_LIMIT"):
        test_no_module_leaves_a_helper_or_constant_behind()


def test_a_constant_another_module_reads_is_not_flagged(tmp_path, monkeypatch):
    """The false positive the fix must not introduce.

    A constant read from a sibling module is not dead, and a guard that says
    it is gets switched off.
    """
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    (tmp_path / "etl").mkdir()
    (tmp_path / "etl" / "thing.py").write_text("SHARED = 7\n", encoding="utf-8")
    (tmp_path / "etl" / "user.py").write_text(
        "from etl.thing import SHARED\nprint(SHARED)\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "tracked",
                        lambda: ["etl/thing.py", "etl/user.py"])
    test_no_module_leaves_a_helper_or_constant_behind()


def guard_over(tmp_path, monkeypatch, files: dict[str, str]):
    """Run the dead-code guard over a synthetic tree instead of this repo.

    The guard's own strictness is otherwise untestable: against the real tree
    it passes, and it passes just as green with each of its checks disabled.
    """
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    (tmp_path / "etl").mkdir()
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "tracked", lambda: sorted(files))
    return test_no_module_leaves_a_helper_or_constant_behind


def test_a_name_IMPORTED_FROM_ELSEWHERE_does_not_spare_a_namesake(
        tmp_path, monkeypatch):
    """The guard used to spare a name any other file merely mentioned.

    Two modules can define the same name — `URL`, `parse` and `population`
    each sit in several files here — and a third that imports one of them was
    enough to mark BOTH live. Four dead names walked through the repo that
    way. Below, `reader` imports `other`'s `URL` and never touches `thing`, so
    `thing`'s `URL` is dead and must be reported.
    """
    guard = guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid/dead\"\n",
        "etl/other.py": "URL = \"https://example.invalid/live\"\n",
        "etl/reader.py": "from etl.other import URL\n\n\ndef _read():\n    return URL\n",
    })
    with pytest.raises(AssertionError, match=r"etl/thing\.py: \['URL'\]"):
        guard()


def test_the_importing_module_still_spares_the_name_it_imports(
        tmp_path, monkeypatch):
    """The other side of the same edge — the false positive to avoid.

    `other`'s `URL` IS read, from a module that imports it, and a guard that
    calls it dead gets switched off within a day.
    """
    guard_over(tmp_path, monkeypatch, {
        "etl/other.py": "URL = \"https://example.invalid/live\"\n",
        "etl/reader.py": "from etl.other import URL\n\n\ndef _read():\n    return URL\n",
    })()


def test_an_async_function_nothing_calls_is_caught(tmp_path, monkeypatch):
    """`ast.AsyncFunctionDef` is not an `ast.FunctionDef`.

    Collecting only the latter left every `async def` out of `defined`, so no
    coroutine could ever be reported dead however unreferenced it was.
    """
    guard = guard_over(tmp_path, monkeypatch,
                       {"etl/thing.py": "async def fetch_nothing():\n    return 1\n"})
    with pytest.raises(AssertionError, match="fetch_nothing"):
        guard()


def test_a_tuple_assignment_is_read_as_two_definitions(tmp_path, monkeypatch):
    """`A, B = 1, 2` has an `ast.Tuple` target, not an `ast.Name`.

    Reading only `Name` targets meant a constant defined this way was
    invisible to the guard — dead or not.
    """
    guard = guard_over(tmp_path, monkeypatch,
                       {"etl/thing.py": "FIRST, SECOND = 1, 2\nprint(FIRST)\n"})
    with pytest.raises(AssertionError, match="SECOND"):
        guard()


def test_a_pytest_fixture_is_not_reported_as_dead(tmp_path, monkeypatch):
    """The false positive that would have switched the guard off.

    A fixture is named only in the parameter lists of the tests taking it, so
    it looks unreferenced to a name walk — `record` has 23 uses in this repo
    and every one is invisible. Decorated functions are exempt for that
    reason, which costs the guard nothing it was catching.
    """
    guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "import pytest\n\n\n@pytest.fixture\ndef record():\n    return 1\n",
    })()

