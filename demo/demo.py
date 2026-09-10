"""A narrated walk through one district's course catalogue, as a graph.

    docker run -d --rm -p 8200:8080 public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
    curl -X POST http://localhost:8200/api/tenants -H 'Content-Type: application/json' \
         -d '{"id":"edtech","name":"EdTech KG"}'
    python -m etl.load_pwcs --url http://localhost:8200 --graph edtech
    python -m demo.demo    --url http://localhost:8200 --graph edtech

Twenty-one questions. Every number on screen is read from the engine as you watch —
nothing here is a stored answer, and each query is printed before it runs so the
audience can see there is no trick in it.

The order is deliberate. It climbs from a question a spreadsheet answers
perfectly to ones it cannot answer at all, in five tiers:

    1   lookup                    Q0–Q4    a spreadsheet wins. Say so
    2   one hop                   Q5–Q8    a join. A spreadsheet is fine
    3   shape of the catalogue    Q9–Q12   awkward, still possible
    4   unknown depth             Q13–Q18  recursive CTEs, and you must know
                                           the depth before you write it
    5   two structures at once    Q19–Q20  unmaintainable

Opening at tier 4 invites "couldn't you have done that in Excel?". The early
questions are what make the later answers credible.

Running it short — the nine that carry a meeting:

    python -m demo.demo --only 0,5,8,11,13,15,16,17,19

Q16 finishes Q15 rather than standing on its own: Q15 counts what closes off
when a student does not pass Algebra 1, and Q16 breaks that number down by
subject, which is the form a head of department can act on. Shown together or
not at all — the count without the subjects invites "which ones?" from the
room, and the answer is one query away.

Q8 and Q11 are in the set for the same reason as each other: an audience that
hears only what is broken stops listening. Q8 is what to reach for when
someone asks how messy data is handled — 138 conditions that are not course
references, counted, kept, and not pretended into edges. Q11 is the positive
counterpart to Q15's twenty-eight: one course that opens six different
careers.

Every traversal is bounded at `*1..8`, tier 4 and tier 5 alike. The tier-5
questions were bounded at 4, which returns the same rows today — the deepest
chain in this catalogue is 4 — but "prerequisites of unknown depth" is the
claim those two questions are making, and a bound tighter than the rest is a
silent ceiling on it. Measured both ways before changing it: 7 rows either way.

**ORDER BY names the source expression, never the alias.** `RETURN length(p) AS
d ORDER BY d` is silently unsorted in 1.1.0 while `ORDER BY length(p)` sorts;
aggregate aliases are the exception and do work. An unsorted list that looks
sorted is the kind of thing an audience spots before you do. Raised as #79.
`tests/test_demo.py` enforces the rule, because a rule that is only written
down is one the next question added here will break silently.

**The asides are not live.** Every figure in a TABLE is read from the engine
as it is shown. The figures in the yellow aside lines — "960 pages", "138
conditions", "Trade and Industrial Education is the most sequenced" — were
read from today's graph and typed here. Re-check them when the catalogue is
reloaded; a table cannot go stale, and these can.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from demo.questions import QUESTIONS, TIERS

DEFAULT_URL = "http://localhost:8200"
BOLD, DIM, CYAN, GREEN, YELLOW, RESET = (
    "\033[1m", "\033[2m", "\033[36m", "\033[32m", "\033[33m", "\033[0m")


class Engine:
    def __init__(self, url: str, graph: str) -> None:
        self.url = url.rstrip("/")
        self.graph = graph

    def run(self, query: str) -> dict:
        payload = json.dumps({"query": query, "graph": self.graph}).encode()
        request = urllib.request.Request(
            f"{self.url}/api/query", data=payload,
            headers={"Content-Type": "application/json"})
        try:
            result = json.loads(urllib.request.urlopen(request, timeout=60).read())
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"\nthe engine rejected a query:\n  "
                             f"{exc.read().decode()[:400]}\n  {query[:200]}")
        except (urllib.error.URLError, OSError) as exc:
            raise SystemExit(f"\nno engine at {self.url} ({exc}).\n"
                             f"Start one and load the catalogue — see the module "
                             f"docstring for the three commands.")
        # The engine answers 200 with an `error` key for a parse failure, so a
        # rejected query is not an HTTP error and would otherwise show as an
        # empty table in front of an audience.
        if "error" in result:
            raise SystemExit(f"\nthe engine rejected a query:\n  "
                             f"{result['error'][:400]}\n  {query[:200]}")
        return result


# --------------------------------------------------------------------------
# Running them
# --------------------------------------------------------------------------

def pause(seconds: float, wait: bool) -> None:
    """Wait for a keypress, or for the clock if there is no one at the keyboard.

    A recorded run has no stdin, and a demo that blocks forever on input is one
    that cannot be recorded.
    """
    if not wait:
        time.sleep(seconds)
        return
    try:
        input(f"{DIM}    ⏎{RESET}")
    except (EOFError, KeyboardInterrupt):
        time.sleep(seconds)


def table(headers: list[str], rows: list[list], limit: int) -> None:
    """Column widths from the header and whatever rows there are — including none.

    The previous line read `max(len(h), *(…) if rows else len(h))`, which Python
    parses as `max(len(h), *(… if rows else len(h)))`: the star applies to the
    whole conditional, so an empty result set unpacked an int and raised
    `TypeError: argument after * must be an iterable`.

    Every query happens to return rows against the catalogue loaded today, which
    is the only reason it never fired. A demo run against a district where every
    pathway lists its courses (Q4), or where 'Studio Art 5' is named differently
    (Q13), would have traceback-crashed in front of an audience — the exact
    failure `preflight` exists to prevent, one step further down.
    """
    widths = [max([len(h)] + [len(str(r[i])) for r in rows[:limit]])
              for i, h in enumerate(headers)]
    print("    " + "  ".join(f"{BOLD}{h:<{w}}{RESET}" for h, w in zip(headers, widths)))
    print("    " + "  ".join("─" * w for w in widths))
    for row in rows[:limit]:
        print("    " + "  ".join(f"{str(v):<{w}}" for v, w in zip(row, widths)))
    if len(rows) > limit:
        print(f"    {DIM}… {len(rows) - limit} more{RESET}")


def records(engine: Engine, query: str) -> list[list]:
    """The rows, or a message naming the query that produced none.

    `engine.run(q)["records"]` gave a bare KeyError on a 200 carrying neither
    `error` nor `records` — the one traceback shape this module otherwise works
    to eliminate, and the worst possible one in front of a room."""
    result = engine.run(query)
    if "records" not in result:
        raise SystemExit(f"\nthe engine answered without records:\n  {query}\n")
    return result["records"]


def holds(engine: Engine, label: str) -> int:
    """How many nodes of a label this graph holds, or 0."""
    rows = records(engine, f"MATCH (n:{label}) RETURN count(n)")
    return int(rows[0][0]) if rows and rows[0] else 0


def ask(engine: Engine, number: int, item: dict, wait: bool, limit: int) -> None:
    print(f"\n{CYAN}{'─' * 78}{RESET}")
    print(f"{CYAN}{BOLD}  Q{number}  {item['question']}{RESET}")
    print(f"{DIM}       tier {item['tier']} — {TIERS[item['tier']]}{RESET}")
    if item.get("aside"):
        print(f"{YELLOW}       {item['aside']}{RESET}")
    print(f"{CYAN}{'─' * 78}{RESET}\n")

    for headers, query in item["queries"]:
        print(f"{DIM}{query}{RESET}\n")
        started = time.time()
        rows = records(engine, query)
        elapsed = (time.time() - started) * 1000
        table(headers, rows, limit)
        print(f"\n    {GREEN}{len(rows)} row(s) in {elapsed:.0f} ms{RESET}\n")
    pause(2.5, wait)


def preflight(engine: Engine) -> None:
    """Refuse to run against a graph that cannot answer these questions.

    Showing an audience an empty table is worse than not starting. The engine
    holds several graphs at once, so this checks it is looking at the right one
    and that the edge every tier-4 question rests on is actually there.
    """
    courses = records(engine, "MATCH (c:Course) RETURN count(c)")[0][0]
    edges = records(engine, "MATCH ()-[e:REQUIRES]->() RETURN count(e)")[0][0]
    if not courses or not edges:
        raise SystemExit(
            f"\nthis graph holds {courses:,} courses and {edges:,} prerequisite "
            f"edges — the demo needs both.\n"
            f"Load it first:  python -m etl.load_pwcs --url {engine.url} "
            f"--graph {engine.graph}\n")

    # Grouped by LABEL SET, not summed per label. Summing four separate counts
    # counts a node carrying two of these labels twice, so `mine` could exceed
    # `total` and print a note about another graph being loaded when none is —
    # a warning that is actively misleading rather than merely absent.
    #
    # `MATCH (n) WHERE n:Course OR …` is the obvious spelling and does not
    # parse in 1.1.0; `labels(n)` in a WHERE does not either. Grouping in the
    # RETURN does, and gives each node exactly once.
    # The national spine (`etl/load_education.py`) writes into this same graph
    # by design, so its labels are OURS rather than somebody else's — without
    # this, loading it printed "another graph is loaded alongside", which is a
    # warning about our own data.
    mine_labels = {"Course", "Subject", "Pathway", "Requirement",
                   "Institution", "Programme", "Completion"}
    total = records(engine, "MATCH (n) RETURN count(n)")[0][0]
    mine = sum(count for held, count in
               records(engine, "MATCH (n) RETURN labels(n), count(n)")
               if mine_labels & set(held or []))
    if total != mine:
        print(f"\n{YELLOW}    note: this engine holds {total:,} nodes and this "
              f"catalogue put in {mine:,} — another graph is loaded alongside. "
              f"Counts below are scoped by label and stay correct.{RESET}")


def chosen(argument: str | None) -> list[int]:
    if not argument:
        return list(range(len(QUESTIONS)))
    picked = []
    for part in argument.split(","):
        if not part.strip():
            continue
        try:
            number = int(part)
        except ValueError:
            # A clean message, not a traceback. The out-of-range case already
            # had one and this did not, which is a difference nobody chose.
            raise SystemExit(f"--only takes question numbers; {part.strip()!r} is not one")
        if not 0 <= number < len(QUESTIONS):
            raise SystemExit(f"no question {number}; there are "
                             f"{len(QUESTIONS)}, numbered 0 to {len(QUESTIONS) - 1}")
        picked.append(number)
    return picked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--graph", default="edtech")
    parser.add_argument("--auto", action="store_true",
                        help="Run without waiting for a keypress.")
    parser.add_argument("--only", metavar="N,N,N",
                        help="Run just these questions, in this order. "
                             "For a short meeting: --only 0,5,8,11,13,15,16,17,19")
    parser.add_argument("--tier", type=int, choices=sorted(TIERS),
                        help="Run only the questions at this tier.")
    parser.add_argument("--rows", type=int, default=12,
                        help="Rows to show per table (default 12).")
    parser.add_argument("--list", action="store_true",
                        help="Print the questions and exit, without an engine.")
    args = parser.parse_args(argv)

    if args.list:
        for number, item in enumerate(QUESTIONS):
            print(f"  {number:>2}  tier {item['tier']}  {item['question']}")
        return 0

    numbers = chosen(args.only)
    if args.tier:
        numbers = [n for n in numbers if QUESTIONS[n]["tier"] == args.tier]
        if not numbers:
            raise SystemExit(f"no questions at tier {args.tier} in that selection")

    wait = not args.auto and sys.stdin.isatty()
    engine = Engine(args.url, args.graph)
    preflight(engine)

    print(f"\n{BOLD}  One district's course catalogue, as a graph{RESET}")
    print(f"{DIM}  Prince William County Schools — catalog.pwcs.edu, published "
          f"openly. No login, no student data.{RESET}")
    print(f"{DIM}  {len(numbers)} questions. Every figure is read from the engine "
          f"as you watch.{RESET}")
    pause(2, wait)

    for number in numbers:
        item = QUESTIONS[number]
        needed = item.get("needs")
        if needed and not holds(engine, needed):
            # **Skipped, and said so.** A question whose data is not loaded
            # would print an empty table, and an empty table in front of an
            # audience reads as a broken product rather than as an absent
            # source. The published snapshot holds the district only.
            print(f"\n{DIM}  Q{number} skipped — this graph holds no "
                  f"{needed}. Load the national spine first:\n"
                  f"        python -m etl.download_education\n"
                  f"        python -m etl.load_education --url {engine.url} "
                  f"--graph {engine.graph}{RESET}")
            continue
        ask(engine, number, item, wait, args.rows)

    print(f"\n{CYAN}{'─' * 78}{RESET}")
    print(f"{BOLD}  Everything above came from pages the district already "
          f"publishes.{RESET}")
    print(f"{DIM}  The tier-4 and tier-5 answers are published nowhere — not by "
          f"the district, not by anyone.{RESET}")

    # **What is NOT here**, which edtech-kg#8 asks for by name. A demo that
    # closes on what it can do invites the room to assume the rest; naming the
    # gaps is what makes the answers above believable.
    print(f"\n{BOLD}  What this graph does not hold:{RESET}")
    for line in (
            "occupations, and the CIP-SOC crosswalk that would join a "
            "programme to the jobs it leads to (#196)",
            "enrolment — completions are loaded, so 'who started' cannot be "
            "compared with 'who finished'",
            "rows recording ZERO awards: 132,284 of them, dropped by default, "
            "so a college that lists a programme and graduates nobody is "
            "absent rather than shown as zero",
            "earnings, and any outcome after the award",
            "any student. Every figure here is a published count."):
        print(f"{DIM}    - {line}{RESET}")
    print(f"{CYAN}{'─' * 78}{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
