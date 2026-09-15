"""Writing to a 1.1.0 graph without MERGE, and counting what was written.

Split from `etl/load_education.py` at the 500-line review limit, and split by
SUBJECT: that module decides WHICH slice to load and what it means; this one
is how anything is written to this engine at all. The hazards are different —
loading the wrong slice measures the wrong thing, writing it wrongly leaves a
graph nobody can trust — and nothing here knows what IPEDS is.

**`MERGE` is not used, and the issue that asked for this asked for `MERGE`.**
docs/first-load.md measured `MERGE` ignoring the constraint's index and
scanning the label instead: 692 statements/sec at 1,500 nodes, 35/sec at
37,141. So every write is a lookup followed by a `CREATE` only if absent.

The engine has no transaction, so there is nothing to roll back to. That is
why `etl/load_education.refuse_unwritable` checks the whole slice before the
first write rather than discovering row 40,000 cannot be quoted.
"""

from __future__ import annotations

from etl.engine import Engine, Refused, Unquotable, lit


def quote(value) -> str:
    """A Cypher literal — `etl.engine.lit`, not a second implementation.

    **This WAS a second implementation, and it was worse in two ways that
    both reached the graph.** It did `str(value)` and always wrapped in `"`,
    so every number landed as a string: `year: "2022"`, `awards: "3"`. The
    schema declares `CREATE INDEX ON :Completion(year)` over that, and
    `sum(c.awards)` — the obvious next query — does not behave. The tell was
    already in this repo's own tests, which had to `int()` their way back out
    of results they had just written.

    It also refused more than the engine does. Any `"` or `\\` was rejected
    outright, so `St. Mary"s College` aborted a 58,000-row load — while `lit`
    picks the other quote character per value and writes it. Only a string
    holding BOTH quote characters is genuinely inexpressible on 1.1.0.

    Two loaders in one graph disagreeing about property typing is the thing
    worth avoiding here; `etl/load_pwcs.py` already used `lit`.

    `Unquotable` is re-raised as `Refused` because the callers catch that —
    though `Refused` means "the engine answered 4xx" and the engine never saw
    this, which is why the message says so.
    """
    try:
        return lit(value)
    except Unquotable as cannot:
        raise Refused(0, f"not sent — {cannot}") from cannot


class Writer:
    """Lookup, then create only if absent — and count both.

    The two round trips are the point, and they are still cheaper than one
    `MERGE`: #169 measured `MERGE` ignoring the constraint's index and
    scanning, falling from 692/sec at 1,500 nodes to 35/sec at 37,141.

    This does not claim "does not degrade" — an earlier draft did, on a
    2,000-row slice, which is exactly the size at which the `MERGE` problem
    is also invisible. `docs/national-spine.md` carries the rate measured
    across the whole load instead.
    """

    def __init__(self, engine: Engine, dry_run: bool = False):
        self.engine = engine
        self.dry_run = dry_run
        self.looked_up = 0
        self.created = 0
        self.already_there = 0
        #: Creates per label and per edge kind. The report compares what the
        #: graph HELD BEFORE plus what this run created against what it holds
        #: now — a whole-graph count against this run's issued count reports
        #: any pre-existing or prior-year data as a gap this run caused.
        self.created_by: dict[str, int] = {}

    def node(self, label: str, key: str, value: str, properties: dict) -> None:
        self.looked_up += 1
        # **A DRY RUN COUNTS THE LOOKUP AND STOPS.** It used to fall through
        # and add a create as well, so `statements_issued` came out roughly
        # double and a dry run could not be compared with the real run it
        # exists to predict. What it would send next depends on an answer it
        # did not ask for.
        if self.dry_run:
            return
        found = self.engine.run(
            f"MATCH (n:{label}) WHERE n.{key} = {quote(value)} "
            f"WITH n RETURN n.{key}").get("records") or []
        if found:
            self.already_there += 1
            return
        self.created += 1
        self.created_by[label] = self.created_by.get(label, 0) + 1
        fields = ", ".join(f"{name}: {quote(v)}"
                           for name, v in properties.items())
        # Concatenated rather than interpolated. An f-string needs the
        # literal brace doubled to emit one, and a doubled brace around a
        # name is exactly the unfilled-template shape
        # `tests/test_repo_layout.py` refuses — this is a public repo and a
        # reader sees an unfilled template before they see anything else.
        # (The comment cannot show the shape either, for the same reason.)
        self.engine.run("CREATE (n:" + label + " {" + fields + "})")

    def edge(self, kind: str, tail: tuple[str, str, str],
             head: tuple[str, str, str],
             properties: dict | None = None) -> None:
        """One edge between two existing nodes, optionally carrying values.

        `properties` exists because `schema/edtech_kg.cypher` puts the
        crosswalk's edition ON the PREPARES_FOR edge — the crosswalk is a
        published claim with a revision history, not a fact, so Q43 can ask
        which edition said so. An edge `MERGE` would not carry them: #163
        records edge `MERGE` ignoring its property map on 1.1.0, which is why
        this looks first and creates second.

        **Both endpoints matched with their own WHERE.** A `MATCH` whose
        endpoints are BOTH already bound does not filter on 1.1.0 — it is
        silently ignored, which `docs/engine-behaviours.md` records — so the
        pattern is written with the endpoints introduced fresh.
        """
        self.looked_up += 1
        if self.dry_run:
            return
        tail_label, tail_key, tail_value = tail
        head_label, head_key, head_value = head

        # **LOOK FIRST — the node path did and this did not.** A second run
        # over the same slice created 2,000 duplicate AT and IN edges: the
        # nodes were idempotent and the edges were not. The loader's own
        # issued-against-held report is what caught it, which is the argument
        # for reading counts back from the graph rather than trusting the
        # count of what was sent.
        #
        # An edge MERGE would not do it either: #163 records edge `MERGE`
        # ignoring its property map on 1.1.0.
        # **The property map participates in the check.** Without it the
        # lookup was (tail, kind, head) only, so loading a later crosswalk
        # edition found every overlapping pair, counted it `already_there`,
        # and never wrote the new `source_edition`. The stated reason the
        # edition rides on the edge is that "a later edition can be told from
        # this one rather than silently replacing it" — as written it did not
        # replace, it declined, which is a different surprise and the same
        # loss. An edge carrying different values IS a different edge here.
        carried_match = "".join(
            f" AND r.{name} = {quote(value)}"
            for name, value in sorted((properties or {}).items()))
        existing = self.engine.run(
            f"MATCH (a:{tail_label})-[r:{kind}]->(b:{head_label}) "
            f"WHERE a.{tail_key} = {quote(tail_value)} "
            f"AND b.{head_key} = {quote(head_value)}{carried_match} "
            f"WITH r RETURN count(r)").get("records") or []
        if existing and existing[0] and existing[0][0]:
            self.already_there += 1
            return

        carried = ""
        if properties:
            carried = " {" + ", ".join(
                f"{name}: {quote(value)}"
                for name, value in sorted(properties.items())) + "}"
        self.engine.run(
            f"MATCH (a:{tail_label}) WHERE a.{tail_key} = {quote(tail_value)} "
            f"WITH a "
            f"MATCH (b:{head_label}) WHERE b.{head_key} = {quote(head_value)} "
            f"WITH a, b "
            f"CREATE (a)-[:{kind}{carried}]->(b)")
        self.created += 1
        self.created_by[kind] = self.created_by.get(kind, 0) + 1
