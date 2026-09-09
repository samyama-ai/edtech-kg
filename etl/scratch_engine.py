"""Refusing to write into a graph that is not ours.

Split from `etl/probe_engine_defects.py` at the 500-line review limit, and
split by SUBJECT the way `engine_bench.py` already was: that module measures
what the engine answers WRONGLY, this one decides whether it is safe to write
to at all. They fail differently — a wrong measurement is a wrong number, and
a wrong decision here is somebody's loaded graph.

**This guard has failed open twice**, and both times in the same direction:
something unmeasurable read as "empty" rather than as "unknown".

  * `/api/status` answering 200 without a `storage.nodes` key left the count
    as None, so the whole check was skipped and ~16,400 unremovable nodes went
    into whatever the probe was pointed at.
  * the leftover count ended `or 0`, turning "I could not measure this" into
    "the graph is empty" — at `storage.nodes` 50,000 it proceeded.

And it rested on a defect holding still: the count ran under `graph="default"`
while this repo loads its district under `graph="edtech"`, and it saw that
data ONLY because graph scoping does not work. An engine build that FIXED
scoping would have this report an empty default on a loaded instance.

So the decision rests on `/api/status`, which is instance-wide, and anything
unmeasurable raises.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from etl.engine import Engine


class Unusable(RuntimeError):
    """The engine refused something the probe needs in order to measure."""


def api(url: str, path: str, method: str = "GET",
        payload: dict | None = None) -> tuple[int, dict | None]:
    """One raw API call, returning the STATUS as well as the body.

    `Engine` is the right client for queries and is used for them. This exists
    because #149 is a claim about status codes — that create returns 201 and
    drop returns 204 while neither scopes anything — and a client that raises
    on status has thrown that evidence away before the probe can read it.
    """
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}", data=body, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as refused:
        raw = refused.read()
        try:
            return refused.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return refused.code, None
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unusable(f"{path}: {gone}") from gone


def still_held(url: str) -> int:
    """How many nodes the ENGINE says it holds, from /api/status.

    **Not a Cypher count.** Two things were wrong with counting in the graph:

      * `scalar(...) or 0` turned "I could not measure this" into "the graph
        is empty". Driven with `storage.nodes` at 50,000 and the count
        answering nothing, the probe proceeded.
      * the count ran under `graph="default"` while this repo loads its
        district under `graph="edtech"`. It saw that data only because graph
        scoping does not work — the same class of defect this probe measures
        for `tenant`. An engine build that FIXED scoping would report an
        empty default on a loaded instance and let the probe run.

    `/api/status` is instance-wide and is the number the refusal should rest
    on. A missing count raises rather than reading as zero.
    """
    status, body = api(url, "/api/status")
    held = ((body or {}).get("storage") or {}).get("nodes")
    if status != 200 or held is None:
        raise Unusable(
            f"{url} answered {status} at /api/status without a "
            f"storage.nodes count, so how much this graph holds could not be "
            f"measured. This probe writes tens of thousands of nodes and "
            f"cannot tidy up after itself; it will not start on an unmeasured "
            f"graph.")
    try:
        return int(held)
    except (TypeError, ValueError) as unreadable:
        # **A non-numeric count is unmeasured, not zero.** `int("many")` gave
        # an uncaught ValueError, so the probe exited 1 with a traceback
        # instead of 2 with a refusal — and a traceback out of a safety guard
        # reads as a bug in the probe rather than as "this engine is not
        # safe to write to".
        raise Unusable(
            f"{url} reported storage.nodes as {held!r}, which is not a "
            f"count. Whether this graph is safe to write to is unknown.") \
            from unreadable


def refuse_unless_scratch(url: str, our_labels) -> None:
    """Raise unless this engine is safe for a probe that cannot tidy up.

    **Checked BEFORE anything is deleted.** The old order issued three
    `DETACH DELETE` statements whenever the node count was truthy and only
    then decided whether to refuse — so on a foreign loaded instance it wrote
    first and declined afterwards. They touch only the probe's own labels, so
    the risk was small, but "refuse without touching it" is the stronger
    property and costs one reordering.
    """
    held = still_held(url)
    if not held:
        return

    # A graph holding ONLY this probe's own labels is its own previous run,
    # and refusing that made the probe single-use: it left ~33,000 nodes
    # behind and then would not start against them, so re-measuring meant
    # destroying and recreating the container. Deleting those is safe and is
    # measured to work — DETACH DELETE is not the broken operation here.
    engine = Engine(url)
    for label in our_labels:
        engine.run(f"MATCH (n:{label}) DETACH DELETE n")
    leftover = still_held(url)
    if leftover:
        raise Unusable(
            f"{url} holds {leftover} node(s) this probe did not write. It "
            f"writes tens of thousands and cannot clean up after itself — "
            f"point it at a scratch engine:\n"
            f"  docker run -d --name sg-defects -p 8224:8080 "
            f"public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0")
