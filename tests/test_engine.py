"""The engine client — how a value becomes a literal, and what a reply means.

`lit()` is the whole of the injection defence, because 1.1.0's `/api/query`
takes no parameters and has no escape sequence inside a string literal. It had
no test at all until review said so.

Reading the catalogue is `tests/test_pwcs_source.py`; writing it is
`tests/test_load_pwcs.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etl import load_pwcs as loader
from etl import pwcs_source as reader
from etl.engine import Unquotable

CACHE = Path(__file__).resolve().parents[1] / "data" / "pwcs"

# `read()` walks 960 pages. Cached they are local and instant; cold it is 960
# requests to a school district from a test run. `data/` is gitignored, so a
# fresh clone has none of it, and these would hammer the source rather than
# fail. Skipped instead — with the command that makes them runnable.
needs_cache = pytest.mark.skipif(
    not CACHE.exists() or not any(CACHE.iterdir()),
    reason="no cached catalogue in data/pwcs — run `python -m etl.probe_pwcs` first")

# --------------------------------------------------------------------------
# lit() — 1.1.0 has no escape sequence, so the quote choice IS the defence
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("plain", "'plain'"),
    ("Governor's School", '"Governor\'s School"'),
    ('say "hi"', "'say \"hi\"'"),
    ("back\\slash", "'back\\slash'"),
    (None, "null"),
    (True, "true"),
    (False, "false"),
    (3, "3"),
    (1.5, "1.5"),
])
def test_a_value_is_wrapped_in_the_quote_it_does_not_contain(value, expected):
    assert loader.lit(value) == expected


def test_a_value_holding_both_quotes_is_refused_not_mangled():
    """1.1.0 supports no escape sequence inside a string literal — not `\\'`,
    not `''`, not `\\"` — so a value containing both quote characters cannot be
    expressed at all, and `/api/query` takes no parameters to fall back on.

    Raising is the point. A course silently loaded under a different name than
    the district published is the failure nothing downstream would show.
    """
    with pytest.raises(Unquotable):
        loader.lit("""Governor's "School\"""")


def test_a_quote_cannot_terminate_the_literal_early():
    """The property being defended: whatever wrapper is chosen, the value does
    not contain it, so nothing can close the string early."""
    for value in ("O'Brien", 'the "best" course', "plain"):
        rendered = loader.lit(value)
        assert rendered[0] == rendered[-1], rendered
        assert rendered[0] not in value, rendered


@needs_cache
def test_no_value_in_this_catalogue_is_unquotable():
    """Stated as a measurement rather than a hope — if a future catalogue
    breaks it, this says so rather than the loader raising mid-run."""
    data = loader.read()
    for record in data["subjects"] + data["courses"] + data["pathways"]:
        for value in (record["url"], record["title"], record.get("requirements_text")):
            if value:
                loader.lit(value)


# --------------------------------------------------------------------------
# the engine client
# --------------------------------------------------------------------------

def test_a_non_finite_float_is_refused_rather_than_sent():
    """`str(float('nan'))` is `nan`, which 1.1.0 does not parse. Sent, the
    statement is rejected at the far end with a message about the whole query
    rather than about the value; refused here, the offending value is named."""
    import math
    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(Unquotable):
            loader.lit(value)


def test_a_bool_is_not_rendered_as_a_number():
    """`isinstance(True, int)` is true, so the bool branch has to come first.
    Load-bearing ordering, and untested until now."""
    assert loader.lit(True) == "true"
    assert loader.lit(False) == "false"


def test_a_rejected_statement_is_an_error_even_though_the_status_was_200():
    """The engine answers 200 with an `error` key for a parse failure."""
    from etl.engine import Engine
    engine = Engine("http://x")

    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"error": "Parse error: unexpected token"}'

    import etl.engine as module
    original = module.urllib.request.urlopen
    module.urllib.request.urlopen = lambda *a, **k: Response()
    try:
        with pytest.raises(RuntimeError, match="Parse error"):
            engine.run("MATCH (n) RETURN n")
    finally:
        module.urllib.request.urlopen = original


def test_a_non_object_response_says_so_rather_than_asking_it_for_a_key():
    """`"error" in result` on a string asks about substrings — a different
    question that happens not to raise."""
    from etl.engine import Engine
    engine = Engine("http://x")

    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'"just a string"'

    import etl.engine as module
    original = module.urllib.request.urlopen
    module.urllib.request.urlopen = lambda *a, **k: Response()
    try:
        with pytest.raises(RuntimeError, match="not an object"):
            engine.run("MATCH (n) RETURN n")
    finally:
        module.urllib.request.urlopen = original


def test_scalar_does_not_confuse_no_rows_with_a_null_value():
    """It returned None for three different things — no rows, an empty row, and
    a null. A caller cannot tell "matched nothing" from "the query is wrong"."""
    from etl.engine import Engine
    engine = Engine("http://x")

    class Response:
        payload = b'{"columns": ["n"], "records": []}'
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.payload

    import etl.engine as module
    original = module.urllib.request.urlopen
    module.urllib.request.urlopen = lambda *a, **k: Response()
    try:
        with pytest.raises(RuntimeError, match="no rows at all"):
            engine.scalar("MATCH (n:Nothing) RETURN count(n)")
    finally:
        module.urllib.request.urlopen = original

