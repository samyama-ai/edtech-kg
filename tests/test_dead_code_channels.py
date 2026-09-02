"""The four ways one module can vouch for a name in another.

Split from `tests/test_dead_code.py` at the 500-line review limit. Split by
SUBJECT: that file is the guard and what it counts as DEFINED — an `async def`,
a tuple target, an annotated assignment, a decorated fixture. This one is the
other half of the question, and the half that has been wrong four times:
what counts as REFERENCED ELSEWHERE.

Each channel pooled across modules before it was narrowed, and every one was
found only after the previous fix made it visible:

    raw file text          any mention anywhere          edtech-kg#125
    attributes             a.NAME vouched for b.NAME     edtech-kg#140
    direct imports         the same, one channel over    edtech-kg#140
    string literals        every literal, everywhere     edtech-kg#145

Two remain deliberately wide, both for the same reason: an unresolvable
receiver means "I could not tell", and turning that into a report of dead code
is what gets a guard switched off.
"""

from __future__ import annotations

import pytest

from tests.test_dead_code import guard_over


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
    with pytest.raises(AssertionError, match=r"etl/thing\.py: \['URL'\]") as caught:
        guard()
    # THE NEGATIVE HALF, and it is the half that tests the resolution. With
    # `resolved = node.module`, `o` binds to `etl`, and `by_receiver["etl"]` is
    # asked whether it matches `etl.thing` — it does not, so `thing` is still
    # reported and the assertion above is satisfied either way. What changes is
    # `other`: its live `URL` loses its only reference and turns into a false
    # positive. Measured — the mutation this test is NAMED for was caught by
    # `test_an_attribute_on_the_RIGHT_module_still_spares_it` and not by this
    # one, which is a test asserting something true regardless of the behaviour
    # under it.
    assert "etl/other.py" not in str(caught.value), (
        "`o` resolved to the package rather than the submodule, so the live "
        "`URL` in etl/other.py is now reported dead")


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


def test_a_name_in_a_string_that_reaches_nothing_does_not_spare_it(
        tmp_path, monkeypatch):
    """The last of the four channels that pooled — and the widest.

    Every string constant in a file was credited to every module that file
    imports, so a name appearing in an assertion message, a `parametrize` id
    or any other literal spared a dead constant of that name everywhere the
    file reached. Below, `reader` mentions `URL` only inside a message.
    """
    guard = guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid/dead\"\n",
        "etl/reader.py": "from etl import thing\n\n\ndef _read():\n"
                         "    assert thing, \"URL is missing\"\n",
    })
    with pytest.raises(AssertionError, match=r"etl/thing\.py: \['URL'\]"):
        guard()


def test_a_name_reached_by_setattr_on_the_right_module_is_spared(
        tmp_path, monkeypatch):
    """The case the channel exists for. `monkeypatch.setattr(m, "THING")`
    reaches a name and nothing else in the file sees it."""
    guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid\"\n",
        "etl/reader.py": "from etl import thing\n\n\ndef _read(monkeypatch):\n"
                         "    monkeypatch.setattr(thing, \"URL\", 1)\n",
    })()


def test_a_setattr_on_a_DIFFERENT_module_does_not_spare_a_namesake(
        tmp_path, monkeypatch):
    """The same `a.NAME` vouches for `b.NAME` shape as the other three
    channels, checked here so this one cannot regress into it."""
    guard = guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid/dead\"\n",
        "etl/other.py": "URL = \"https://example.invalid/live\"\n",
        "etl/reader.py": "from etl import other\nfrom etl import thing\n\n\n"
                         "def _read(monkeypatch):\n"
                         "    monkeypatch.setattr(other, \"URL\", 1)\n"
                         "    return thing\n",
    })
    with pytest.raises(AssertionError, match=r"etl/thing\.py: \['URL'\]") as caught:
        guard()
    assert "etl/other.py" not in str(caught.value), (
        "the setattr on `other` no longer spares its own URL")


def test_a_setattr_whose_receiver_is_not_an_alias_still_spares(
        tmp_path, monkeypatch):
    """`setattr(probe.crosswalk, "LOCAL")` names its target through an
    attribute chain, and this repo does that in five places. Unresolvable, so
    pooled — the same lenience `loose_attributes` gets."""
    guard_over(tmp_path, monkeypatch, {
        "etl/thing.py": "URL = \"https://example.invalid\"\n",
        "etl/reader.py": "from etl import thing\n\n\nclass Holder:\n    inner = None\n\n\n"
                         "def _read(monkeypatch):\n"
                         "    monkeypatch.setattr(Holder.inner, \"URL\", 1)\n"
                         "    return thing\n",
    })()
