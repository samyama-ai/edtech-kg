"""Talking to Samyama-Graph 1.1.0.

Separated from any one loader because the next loader needs exactly this, and
because `etl/load_pwcs.py` reached 616 lines — over the size review will read,
which meant the file went unexamined.

Two engine facts shape everything here, both measured:

  * `/api/query` accepts only `query` and `graph`. **No parameters.** Every
    value is interpolated into statement text, so `lit()` is load-bearing.
  * **There is no escape sequence inside a string literal** — not `\'`, not
    `''`, not `\"`. A backslash is stored as itself. The quote character is the
    only thing that ends a literal.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class Engine:
    def __init__(self, url: str, graph: str = "default") -> None:
        self.url = url.rstrip("/")
        self.graph = graph
        self.statements = 0
        self.retries = 0

    def run(self, query: str, attempts: int = 4) -> dict:
        payload = json.dumps({"query": query, "graph": self.graph}).encode()
        result = None
        for attempt in range(attempts):
            request = urllib.request.Request(
                f"{self.url}/api/query", data=payload,
                headers={"Content-Type": "application/json"})
            try:
                result = json.loads(urllib.request.urlopen(request, timeout=120).read())
                break
            except urllib.error.HTTPError as exc:
                body = exc.read().decode()[:300]
                # 4xx will fail identically every time; retrying only delays
                # the report. Transient 5xx are worth another go.
                if exc.code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                    self.retries += 1
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"{exc.code} on: {query[:160]}\n{body}") from exc
            except (urllib.error.URLError, OSError, TimeoutError,
                    json.JSONDecodeError) as exc:
                if attempt < attempts - 1:
                    self.retries += 1
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"unreachable on: {query[:160]}\n{exc}") from exc
        # The engine answers 200 with an `error` key for a parse failure, so a
        # rejected statement is not an HTTP error and would otherwise pass.
        if result is None or "error" in result:
            raise RuntimeError(f"{(result or {}).get('error', 'no response')}\n"
                               f"  on: {query[:160]}")
        self.statements += 1
        return result

    def scalar(self, query: str):
        records = self.run(query)["records"]
        return records[0][0] if records and records[0] else None


def upsert(engine: Engine, label: str, key: str, value: str, props: dict) -> None:
    """MERGE the key, then SET the rest — two statements, deliberately.

    **`MERGE (n:L {k: v}) SET n.p = x` does not parse in 1.1.0.** The parser
    accepts `ON CREATE SET` and `ON MATCH SET` after a MERGE but not a bare
    SET, which is a Cypher form every other implementation takes. Raised as #75.

    `ON CREATE SET` alone would be one statement and is the obvious workaround —
    but it fires only on insert, so re-running after the district renames a
    course leaves the old name in the graph with nothing to show for it. A
    separate MATCH … SET always refreshes, which is what a re-runnable loader
    has to do.
    """
    engine.run(f"MERGE (n:{label} {{{key}: {lit(value)}}})")
    if props:
        assignments = ", ".join(f"n.{name} = {lit(v)}" for name, v in props.items())
        engine.run(f"MATCH (n:{label} {{{key}: {lit(value)}}}) SET {assignments}")


class Unquotable(Exception):
    """A value 1.1.0 has no way to express as a string literal."""


def lit(value) -> str:
    """A Cypher literal. 1.1.0 takes no parameters, so this is the defence.

    **1.1.0 supports no escape sequence inside a string literal.** Measured
    against the engine, all three of these are parse errors:

        'Governor\\'s'      backslash escape
        'Governor''s'       doubled quote, the SQL form
        "say \\"hi\\""       backslash escape in a double-quoted string

    A backslash is not an escape character at all; it is stored as itself. So
    the quote character is the only thing that ends a literal, and the only way
    to carry one is to wrap the value in the *other* quote. Raised as #76.

    That leaves one value this engine cannot express: a string containing both
    an apostrophe and a double quote. It raises rather than mangling, because
    the alternative is a course silently loaded under a different name than the
    district published — and nothing downstream would show it.

    `regulatory-affairs-kg/etl/cypher.py` reached the same conclusion against
    the same engine and selects the quote per value too — worth knowing that two
    independent measurements agree. Its MCP server does not: `quoted()` escapes
    with backslashes, so every tool call carrying an apostrophe is a statement
    the engine rejects. Raised there as #24.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if "'" not in text:
        return f"'{text}'"
    if '"' not in text:
        return f'"{text}"'
    raise Unquotable(
        f"1.1.0 cannot express a string holding both quote characters, and "
        f"there is no escape sequence to fall back on: {text[:120]!r}")
