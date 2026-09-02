"""Symbols a split left behind, which no linter this repo runs reports.

Split from `tests/test_repo_layout.py` at the 500-line review limit — six
reviews here have reported a file as too large and reviewed nothing inside it.
Split by SUBJECT: that file checks the repo's SHAPE — the directories exist,
no template placeholder survives, the demo set agrees with itself. This one is
a single guard and the tests that keep it honest.

Unused module-level functions and constants are flagged by nothing else:
`pyflakes` sees a name assigned at module scope and stops. Three file splits in
three rounds each left something behind, invisible to a green suite and a clean
style run.

The guard has been wrong twice, both times in the sparing direction, and both
are tests below rather than memories:

- It matched bare names in RAW TEXT, so any file mentioning a name spared it.
  `URL`, `parse` and `population` walked through (edtech-kg#125).
- It pooled every attribute in a file and handed the pool to every module that
  file imported, so `a.NAME` vouched for `b.NAME` — and `from etl import x as
  y` recorded `y` against the PACKAGE, so the pool went to everything under
  `etl.` (edtech-kg#140).
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return [n for n in out.stdout.split("\0") if n]


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

    modules = {module_of(name) for name in sources}

    referenced_elsewhere: dict[str, set[str]] = {n: set() for n in sources}
    for other, text in sources.items():
        try:
            other_tree = ast.parse(text)
        except SyntaxError:
            continue
        # DIRECT IMPORTS BY MODULE, for the same reason as the attributes
        # below. A flat set was OR'd into every module this file imports, so
        # `from etl.other import URL` spared `etl/thing.py`'s dead `URL` as
        # soon as the file also imported `thing` — `a.NAME` vouching for
        # `b.NAME` through the other channel.
        #
        # THE NARROWING HAS A FLOOR. `from etl import x` where `x` is not a
        # tracked submodule still resolves to `etl`, so those names stay
        # package-wide: deciding whether `x` is a symbol or a module without
        # importing is only possible when a file answers it.
        direct_by_module: dict[str, set[str]] = {}
        aliases: dict[str, str] = {}      # local alias -> module it refers to
        for node in ast.walk(other_tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    submodule = f"{node.module}.{alias.name}"
                    resolved = submodule if submodule in modules else node.module
                    direct_by_module.setdefault(resolved, set()).add(
                        alias.asname or alias.name)
                    # THE SUBMODULE, not the package. `from etl import x as y`
                    # is an ImportFrom whose `node.module` is `etl`, so `y` was
                    # recorded against the PACKAGE — and the import test below
                    # matches `etl.anything` against `etl`, which credited
                    # every attribute reached through `y` to every module under
                    # `etl.`. Measured: `etl/probe_codesets.NO_MATCH` was dead
                    # and survived because a test writes
                    # `probe_apprenticeship.NO_MATCH`, a different module's
                    # live constant of the same name (edtech-kg#140).
                    #
                    # A name in `from X import n` may be a submodule or a
                    # symbol, and only the first is a module. Resolved against
                    # the files this repo tracks rather than by importing
                    # anything.
                    aliases.setdefault(alias.asname or alias.name, resolved)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    # `setdefault`, matching the branch above. The two used
                    # different rules — first-binding-wins here, last-wins
                    # there — which is not wrong today and is one dict with two
                    # rules for whoever edits it next. FIRST wins, because a
                    # rebinding later in a file is far more often a local shadow
                    # than a correction of the import.
                    aliases.setdefault(alias.asname or alias.name.split(".")[0],
                                       alias.name)
        # ATTRIBUTES BY RECEIVER. A bare `{n.attr for ...}` pooled every
        # attribute in the file and handed the pool to every imported module,
        # so `a.NAME` vouched for `b.NAME`. Only attributes whose receiver is
        # an alias for the target module count now; attributes on anything
        # else — a local object, an unimported name — are kept in
        # `loose_attributes` because a receiver this cannot resolve should not
        # silently become a false report of dead code.
        by_receiver: dict[str, set[str]] = {}
        loose_attributes: set[str] = set()
        for node in ast.walk(other_tree):
            if not isinstance(node, ast.Attribute):
                continue
            if isinstance(node.value, ast.Name) and node.value.id in aliases:
                by_receiver.setdefault(aliases[node.value.id], set()).add(node.attr)
            else:
                loose_attributes.add(node.attr)
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
            direct = {name for alias_module, names in direct_by_module.items()
                      for name in names
                      if alias_module == module or alias_module.startswith(module + ".")}
            attributes = loose_attributes | {
                attr for alias_module, attrs in by_receiver.items()
                for attr in attrs
                if alias_module == module or alias_module.startswith(module + ".")}
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
    way.

    `reader` imports BOTH, which is the shape that reproduces it — the guard
    only reaches the name check for a module the file imports, so a tree where
    the sparing file never imports the target proves nothing. This test had
    that hole and passed over a `direct` set that was still pooled across
    modules, which is the attribute defect one channel over.
    """
    guard = guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid/dead\"\n",
        "etl/other.py": "URL = \"https://example.invalid/live\"\n",
        "etl/reader.py": "from etl.other import URL\nfrom etl import thing\n\n\n"
                         "def _read():\n    return URL, thing\n",
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


def test_an_attribute_on_a_SIBLING_module_does_not_spare_a_namesake(
        tmp_path, monkeypatch):
    """The gap edtech-kg#140 was raised for, and it is mine.

    The guard pooled every attribute in a file and handed the pool to every
    module that file imported, so `a.NAME` vouched for `b.NAME`. Worse, the
    alias resolution made "imports" almost meaningless: `from etl import x as
    y` is an `ImportFrom` whose `node.module` is `etl`, the PACKAGE, so `y` was
    recorded against `etl` and the import test matched `etl.anything`.

    Measured on #139: `etl/probe_codesets.NO_MATCH` was dead and survived,
    because a test writes `probe_apprenticeship.NO_MATCH` — a different
    module's live constant of the same name. `from etl import x as y` is the
    dominant import style here, so this was not an edge case.

    Below, `reader` reaches `other.URL` and never touches `thing`.
    """
    # `reader` imports BOTH, which is the shape that reproduces it: the guard
    # only reaches the attribute check for a module the file imports, so a
    # tree where the sparing file never imports the target proves nothing.
    # `tests/test_probe_apprenticeship.py` imported both for the same reason —
    # a test module usually does.
    guard = guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid/dead\"\n",
        "etl/other.py": "URL = \"https://example.invalid/live\"\n",
        "etl/reader.py": "from etl import other\nfrom etl import thing\n\n\n"
                         "def _read():\n    return other.URL, thing\n",
    })
    with pytest.raises(AssertionError, match=r"etl/thing\.py: \['URL'\]"):
        guard()


def test_an_attribute_on_the_RIGHT_module_still_spares_it(tmp_path, monkeypatch):
    """The bound that matters more. A guard that starts reporting live names
    gets switched off, and then nothing is watching at all."""
    guard_over(tmp_path, monkeypatch, {
        "etl/other.py": "URL = \"https://example.invalid/live\"\n",
        "etl/reader.py": "from etl import other\n\n\ndef _read():\n"
                         "    return other.URL\n",
    })()


def test_an_aliased_submodule_import_resolves_to_the_submodule(tmp_path, monkeypatch):
    """`from etl import other as o` — the spelling this repo actually uses.

    The alias has to resolve to `etl.other` and not to `etl`, or every module
    under the package is credited again through a different door.
    """
    guard = guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid/dead\"\n",
        "etl/other.py": "URL = \"https://example.invalid/live\"\n",
        "etl/reader.py": "from etl import other as o\n\n\ndef _read():\n"
                         "    return o.URL\n",
    })
    with pytest.raises(AssertionError, match=r"etl/thing\.py: \['URL'\]"):
        guard()


def test_an_attribute_whose_receiver_cannot_be_resolved_still_spares(
        tmp_path, monkeypatch):
    """A receiver this cannot resolve is not evidence of ABSENCE.

    `self.URL`, `config().URL`, an attribute on a local object — the guard
    cannot say which module those belong to, so they keep sparing every
    imported module. Narrowing them too would turn "I could not tell" into a
    report of dead code, and a false positive is what gets a guard deleted.
    """
    guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid\"\n",
        "etl/reader.py": "from etl import thing\n\n\n"
                         "class Holder:\n    URL = 1\n\n\n"
                         "def _read():\n    return Holder().URL\n",
    })()
