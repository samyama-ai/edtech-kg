"""Reading the schema — one view of its FILES, shared by both
test modules that parse it.

Split out when `tests/test_schema_cypher.py` reached 599 lines and was skipped
whole by review as too large to read. The parse tests and the engine tests are
different jobs with different requirements — one needs nothing, the other needs
a running instance — and the helpers were the only reason they shared a file.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from etl import cypher_script
from etl.cypher_script import SCHEMA_FILES  # noqa: F401  (re-exported)

ROOT = Path(__file__).resolve().parent.parent

# `SCHEMA_FILES` is re-exported from the loader above, never re-declared. This
# module used to carry its own copy of the tuple, which is how "the schema"
# came to have five independent definitions after #157 — see
# `etl.cypher_script.SCHEMA_FILES` for what that cost.
#
# There is deliberately no `SCHEMA` naming one file. It existed through the
# split as a convenience and was a footgun: every test that reached for it got
# tier 1 and reported on "the schema", which is how the 960-course guard came
# to check the file the figure had just moved out of.
#
# A plain comment, not `#:` — that form documents the symbol BELOW it and
# there is none here, so the block was attached to nothing.


@lru_cache(maxsize=1)
def schema_text() -> str:
    """The schema files, joined — **the loader's own function, cached**.

    This was a second copy of the same two-line join. The tuple got one home
    in this PR and the READER did not, which is the same drift one level down:
    two joiners that agree today, with nothing asserting they will.

    Cached because `code()`, `patterns()` and `constraint_line()` each re-read
    on every call and `constraint_line()` runs once per label, so a single
    test run read the same unchanging files dozens of times. The loader must
    NOT cache — it is applied to a live engine and the files can change under
    a long-running process — which is why the cache lives here and not there.
    """
    return cypher_script.schema_text()


def sole_file_stating(needle: str, what: str) -> Path:
    """The one schema file containing `needle`, or a failure naming the count.

    Reading "the schema" as one joined string is convenient and it is how four
    separate guards ended up weaker than they read. `str.find` on the join
    returns the FIRST occurrence, so a heading in tier 1 shadows the real one
    in tier 2 and the slice between two anchors can silently span the file
    boundary — the assertion still passes, on the wrong text, and the failure
    message when it does fail names `schema/*.cypher` rather than a file
    anyone can open.

    Two anchors that must bracket a block must therefore be found in the SAME
    file. This returns that file so callers can say so.
    """
    carrying = [f for f in SCHEMA_FILES if needle in f.read_text(encoding="utf-8")]
    assert carrying, (
        f"no schema file states {what} ({needle!r}) — searched "
        f"{', '.join(f.name for f in SCHEMA_FILES)}")
    assert len(carrying) == 1, (
        f"{what} ({needle!r}) appears in {len(carrying)} schema files "
        f"({', '.join(f.name for f in carrying)}); a marker in two files means "
        f"every guard sliced on it reads whichever sorts first")
    return carrying[0]


SCHEMA_DOC = ROOT / "docs" / "schema.md"
QUESTIONS = ROOT / "docs" / "questions.md"


BLOCK_COMMENT = re.compile(r"/\*")


def strip_comment(line: str) -> str:
    """Drop a `//` comment, but not a `//` inside a string literal.

    **Only `//`.** A `/* … */` block comment is legal Cypher and 1.1.0 accepts
    it — measured — so one added to the schema would pass straight through here
    into a statement, and the failure would surface as "this statement is not a
    constraint or an index", pointing at the wrong thing. The file uses `//`
    throughout; `code()` refuses a block comment rather than half-parsing one.

    Splitting unconditionally truncates `MERGE (n {url: 'https://x'})` at the
    scheme. No statement in the schema carries a URL today — the URLs are all
    in comments — so the naive split has never done damage, and would the day
    a default or an example value was added.

    Quote tracking only, no parser: 1.1.0 has no escape sequence inside a
    string literal, so a quote always opens or closes one and never appears
    within. Same function as `etl/load_pwcs.strip_comment`, and deliberately
    not imported from it — these tests must not depend on the code they check.
    """
    quote = None
    for i, character in enumerate(line):
        if quote:
            if character == quote:
                quote = None
        elif character in "'\"":
            quote = character
        elif character == "/" and line[i:i + 2] == "//":
            return line[:i]
    return line


def code(text: str | None = None) -> str:
    """The file with every comment removed — the single view of what executes.

    Trailing comments count, not only whole-comment lines. `CREATE INDEX ON
    :Completion(year);  // annual` would otherwise carry the comment into the
    statement, and a `;` inside one would split a statement in half.

    `text` is here so the tests can exercise THIS function against a hazard the
    file does not contain yet. A test that reimplements the stripping on a
    synthetic line proves the technique and says nothing about the code that
    ships — the dead-path test, which this repo has shipped before.
    """
    source = schema_text() if text is None else text
    assert not BLOCK_COMMENT.search(source), (
        "this file uses `//` comments throughout and the readers here strip "
        "only those. A `/* … */` block is legal Cypher and 1.1.0 accepts it, "
        "so it would pass through into a statement — refused here rather than "
        "half-parsed, because a partial comment parser is how a statement gets "
        "silently truncated.")
    return "\n".join(strip_comment(line) for line in source.splitlines())


def statements(text: str | None = None) -> list[str]:
    """Executable statements, comments stripped."""
    return [s.strip() for s in " ".join(code(text).splitlines()).split(";") if s.strip()]


# Both constraint spellings. The file uses the `ON … ASSERT` form because the
# Neo4j-5 `FOR … REQUIRE` form does not parse in 1.1.0 — but a pattern pinned to
# only that form returns an EMPTY list the day the engine catches up and someone
# modernises the file, and every containment check against an empty set passes
# vacuously. The same hazard `first_column` guards against, one file over.
CONSTRAINT = re.compile(
    r"CREATE CONSTRAINT (?:\w+ )?(?:IF NOT EXISTS )?"
    r"(?:ON|FOR) \(\w+:(\w+)\)")


def labels(text: str | None = None) -> list[str]:
    """From the stripped text, so a commented-out constraint is not counted.

    `labels()` and `edges()` used to regex the raw file while `statements()`
    read the stripped one — two views of one file, which is the defect this
    repo keeps finding.

    Whitespace is collapsed before matching, for the same reason `first_column`
    is reflow-tolerant: the pattern spans `CREATE CONSTRAINT … ON (n:Label)`,
    so a declaration wrapped across two lines matches NOTHING, and the label
    then drops silently out of every containment check that reads this list.
    A missing label does not fail those checks — it makes them pass on a
    smaller set, which is the vacuous pass this file exists to prevent.
    """
    return CONSTRAINT.findall(" ".join(code(text).split()))


def patterns(text: str | None = None) -> str:
    """The edge patterns, which live in COMMENTS because they carry no
    constraint — so this one reads the RAW file, deliberately.

    Takes `text` for the same reason `code()` does: so a test can drive it
    with markup the file does not contain, rather than reimplementing it.
    """
    return schema_text() if text is None else text


def edges(text: str | None = None) -> set[str]:
    return set(re.findall(r"-\[:([A-Z_]+)", patterns(text)))


def first_column(table: str) -> set[str]:
    """The backticked names in a markdown table's first column.

    Whitespace-tolerant. The previous patterns required exactly one space
    either side of the pipe, so a formatter reflowing the table — or anyone
    aligning the columns — would yield an EMPTY set and every containment
    check against it would pass vacuously. Callers assert the result is
    non-empty for the same reason.

    Only the first column is read; collecting every backticked word in the
    table picks up the labels in the From/To column, and an edge sharing a name
    with a label would then pass without being documented.
    """
    names: set[str] = set()
    for row in table.splitlines():
        cell = re.match(r"\s*\|([^|]*)\|", row)
        if not cell:
            continue
        names |= set(re.findall(r"`(\w+)`", cell.group(1)))
    return names


def section(text: str, after: str, before: str | None = None) -> str:
    """The slice of a document between two headings, or a readable failure.

    `text.split(heading)[1]` raises `IndexError` the day a heading is reworded
    — a bare traceback naming a list index, from which nobody can tell that a
    document was renamed. Every guard in these files rests on slicing a
    document by its own headings, so the failure mode is worth naming once
    here rather than at each call site.
    """
    parts = text.split(after)
    assert len(parts) > 1, f"no heading {after!r} in this document any more"
    # A repeated heading is REFUSED, not guessed at. A banner's text can appear
    # in prose above the banner itself — "everything under TIER 2 — modelled is
    # unpopulated" mentions the heading — and slicing on the first hit then
    # truncates the section to the prose preceding it, silently shrinking what
    # every caller checks. Picking the last hit instead only moves the guess;
    # two occurrences is a document the reader cannot resolve, and saying so is
    # the honest answer.
    assert len(parts) == 2, (
        f"{after!r} appears {len(parts) - 1} times; the slice is ambiguous, so "
        f"a caller would be checking an arbitrary part of the document")
    tail = parts[1]
    if before is None:
        return tail
    parts = tail.split(before)
    assert len(parts) > 1, (
        f"{before!r} no longer follows {after!r} in this document")
    return parts[0]


# One declaration, whole, however it is wrapped. `code()` preserves lines, so a
# declaration reflowed across two of them cannot be found by a line-local
# substring — which is the blind spot `labels()` was fixed for, and which two
# key-composition tests reintroduced by locating constraints their own way.
DECLARATION = re.compile(
    r"CREATE CONSTRAINT (?:\w+ )?(?:IF NOT EXISTS )?"
    r"(?:ON|FOR) \(\w+:(\w+)\) (?:ASSERT|REQUIRE) \w+\.(\w+) IS UNIQUE")


def declarations(text: str | None = None) -> list[tuple[str, str]]:
    """Every `(label, key)` the schema declares, wrap-tolerant.

    Whitespace is collapsed before matching, for the reason `labels()` gives:
    a declaration wrapped at the line width matches nothing, drops out of the
    list, and every containment check against the smaller list passes.

    **Every `CREATE CONSTRAINT` must match, and that is asserted.** The pattern
    reads `… ASSERT n.p IS UNIQUE`; a form it does not know — `IS NODE KEY`, a
    composite, anything a later engine adds — would otherwise drop out
    silently, which is the same vacuous pass this module exists to prevent,
    one level up. 1.1.0 does not parse `IS NODE KEY` today (measured), so this
    is a guard against the file changing rather than against the file as it is.
    """
    flat = " ".join(code(text).split())
    found = DECLARATION.findall(flat)
    declared = len(re.findall(r"CREATE CONSTRAINT\b", flat))
    assert len(found) == declared, (
        f"{declared} CREATE CONSTRAINT statements in the schema and only "
        f"{len(found)} match the declaration pattern. The unmatched ones are "
        f"invisible to every check that reads this list — widen the pattern "
        f"rather than leaving them out.")
    return found


# How many lines one declaration may be wrapped across. Five is generous — the
# longest in the file is one — but the number matters, so a declaration wrapped
# wider than this must FAIL rather than silently not be found.
WRAP_LIMIT = 5


def constraint_line(label: str, text: str | None = None) -> int | None:
    """The **0-indexed** line the declaration of `label` ends on.

    0-indexed because callers slice `lines[start:at]` to read the comment block
    above it, and an off-by-one there is a comment block that silently excludes
    its first line. Stated here because the convention is not visible at the
    call site.

    Callers want that comment block, so they need a line number — but they were
    finding it with `f":{label})" in line`, the line-local test that misses a
    wrapped declaration. This walks a growing window instead.

    `None` means the label is not declared at all. It does NOT mean "declared
    but wrapped too wide": that case raises, because a silent `None` there is
    indistinguishable from "not declared", and the caller's assertion would
    then report the wrong fault.
    """
    # **Through `code()`, so a COMMENTED-OUT declaration cannot match.** This
    # split the raw text, and `labels()` — which does walk `code()` — was
    # already guarded by `test_a_commented_out_constraint_is_not_counted`.
    # This was the one path that skipped it, and `declaration_site` then
    # resolved a label to a comment in the wrong file: measured, blanking
    # Place's documentation in tier 2 and adding
    # `// CREATE CONSTRAINT ON (pl:Place) …` to tier 1 left the suite green
    # while two guards read their documentation window from a file declaring
    # nothing.
    #
    # `text` for the same reason `code()` takes it: so a test can drive this
    # against a hazard the real file does not contain — here, a declaration
    # wrapped wider than the window.
    #
    # Line numbers are preserved because `strip_comment` blanks a comment
    # rather than dropping its line — so the index this returns still points
    # at the same line of the ORIGINAL text, which is what callers slice.
    lines = code(schema_text() if text is None else text).splitlines()
    for end in range(len(lines)):
        window = " ".join(" ".join(lines[max(0, end - WRAP_LIMIT + 1):end + 1]).split())
        for found, _ in DECLARATION.findall(window):
            if found == label:
                return end

    declared = {name for name, _ in declarations(text)}
    assert label not in declared, (
        f"{label} IS declared, but its declaration could not be located within "
        f"{WRAP_LIMIT} lines — it is wrapped wider than that. Returning None "
        f"here would be indistinguishable from 'not declared at all'.")
    return None


def declaring_file(label: str) -> Path:
    """Which schema file declares `label`. Wrap-tolerant, comment-blind.

    Callers were locating the Pathway declaration with the literal string
    `"CREATE CONSTRAINT ON (pw:Pathway)"`, which is the line-local test
    `constraint_line()` exists to replace — reflowing that declaration across
    two lines turned six tests red saying "no schema file states the Pathway
    key", which is loud, wrong, and expensive to diagnose.
    """
    return declaration_site(label)[0]


def declaration_site(label: str) -> tuple[Path, list[str], int]:
    """The file declaring `label`, its lines, and the 0-indexed line it ends on.

    Callers read a window of comment lines ABOVE a declaration. Indexing into
    the joined text lets that window reach backwards across the file boundary,
    so a tier-2 constraint can be "documented" by the tail of tier 1 — latent
    today only because tier 2's first constraint happens to sit far enough
    below its own file's top.

    Raises rather than returning None: every caller asserts the label is
    declared immediately afterwards, and a shared "not found" that each of
    them re-checks is a check that one of them will eventually forget.
    """
    # EXACTLY ONE, not the first. Returning the first hit reintroduced the
    # shadowing this helper was written to remove — a second declaration in
    # another file would be invisible, and which one you got would depend on
    # tuple order. `sole_file_stating` above already refuses that; the two
    # now differ only in what they return, not in how strict they are.
    found = []
    for path in SCHEMA_FILES:
        text = path.read_text(encoding="utf-8")
        at = constraint_line(label, text)
        if at is not None:
            found.append((path, text.splitlines(), at))
    assert found, (
        f"{label} is not declared in any schema file "
        f"({', '.join(f.name for f in SCHEMA_FILES)})")
    assert len(found) == 1, (
        f"{label} is declared in {len(found)} schema files "
        f"({', '.join(p.name for p, _, _ in found)}). Every guard that reads "
        f"a documentation window for it would read whichever sorts first.")
    return found[0]
