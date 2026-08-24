# MCP server

**Not implemented.** This directory holds the package and this note, and nothing
else — deliberately, so that what is missing is legible rather than disguised.

## Why it is empty rather than absent

`mcp_server/` is part of the layout every `*-kg` repo shares, and MCP is how a
grounded answer is actually delivered — the ecosystem's central claim is that an
LLM querying a knowledge graph answers far more accurately than one guessing,
and MCP is the path that makes that true in practice. A KG with no MCP server
cannot demonstrate the thing it exists to demonstrate.

So the directory stays. What was here before did not.

## What was removed, and why that was worse than nothing

The template left a `server.py` exposing one tool:

```python
@mcp.tool()
def example_query(limit: int = 5) -> list[dict]:
    """Replace with a real domain query against the Samyama graph engine."""
    return []
```

A tool that returns `[]` is the worst possible state. It registers, it answers,
and an agent calling it reads the empty list as *"the graph holds nothing that
matches"* — a confident wrong answer, which is the failure this repo works
hardest to avoid everywhere else. The sibling repo hit exactly this: its MCP PR
is titled "eight tools that query the graph, **replacing two that returned
`[]`**".

A `config.yaml` naming a tenant for a server that does not run went with it.

## What it should expose

The graph answers questions about one district's catalogue today — 1,098 nodes,
1,417 edges. The tools worth building are the ones `demo/demo.py` already
proves are answerable, because each is a traversal that returns real rows now:

| Tool | Question |
|---|---|
| `prerequisites_for(course)` | What must a student take first, transitively? |
| `blast_radius(course)` | Fail this course — what closes off, and across how many subjects? |
| `courses_in_pathway(pathway)` | What is a published pathway made of? |
| `pathways_including(course)` | Which routes does this course sit on? |
| `route_between(a, b)` | Shortest prerequisite chain between two courses. |
| `orphans()` | Courses on no chain at all — 395 of 791, which is the figure that surprises people. |

Two engine facts constrain any implementation, both measured and both recorded
in `etl/engine.py`: `/api/query` takes **no parameters**, so every value is
interpolated and `lit()` is the whole of the injection defence; and there is no
escape sequence inside a string literal, so a search term holding both quote
characters cannot be expressed at all.

That second one is a trap the sibling repo walked into and its review caught: a
term altered to be representable no longer matches, so the tool returns `[]`
with no error — the same confident-empty-answer failure, arriving by a different
route. Any tool built here has to distinguish *"no rows"* from *"your term
cannot be expressed"* from *"the engine is down"*.

`fastmcp` is declared as the `mcp` optional extra rather than a hard dependency,
so `pip install -e .` does not pull a library nothing imports yet:

```bash
pip install -e '.[mcp]'
```
