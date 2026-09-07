"""Every published Registry course, asked whether it states a prerequisite.

#58. `etl/probe_registry.py` samples 600 courses at a fixed stride and finds
`ceterms:prerequisite` — CTDL's typed Course->Course edge — used **zero** times.
600 spread across 47,862 is a real sample, and it still cannot settle the
question the docs rest on, because the finding is a claim about a RARE event:
absence in a 1.3% sample is consistent with a few hundred uses.

The difference is a decision, not a detail:

    zero in 47,862   we adopt the term knowing we would be its first user —
                     a gap in the ecosystem, and worth saying so out loud
    some uses        those publishers are a worked example of the shape we
                     want, and a source of real resolved prerequisites

Either answer is useful. Not knowing which is not.

**It asks the sample's question, not a similar one.** Every classification here
comes from `etl.registry_courses.classify`, which `probe_registry` also calls —
so a figure that replaces the sample's cannot differ because the two counted
differently. That module exists for this reason.

## Being polite to a service we do not pay for

958 pages, measured at 3-5s each: about an hour, and the Registry is its own
rate limiter — the wait is server-side, so an added delay buys politeness the
service did not ask for while doubling the window in which something can fail.
`--delay` exists for when it does ask.

What politeness actually requires here is **not re-walking**. A run that dies
at page 900 and starts again from page 1 costs the Registry twice, so progress
is checkpointed after every page and `--resume` continues from it.

## Refusing to report a partial as a total

A sweep that stops early has measured a prefix of the Registry, and a prefix is
not a census. The result carries `complete`, and the report REFUSES to print
the headline figure unless every page was read — an incomplete sweep prints
what it covered and says what it did not. That is the same rule
`probe_registry` follows in `describe()`, which reports the pages READ rather
than the pages planned.

    python -m etl.sweep_prerequisites               # the whole Registry
    python -m etl.sweep_prerequisites --resume      # continue a dead run
    python -m etl.sweep_prerequisites --pages 20    # a short run, for testing
    python -m etl.sweep_prerequisites --record      # write the record

No third-party dependency, as with the probes.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys
import time

from etl.registry_courses import classify, courses_in, publisher_of
from etl.registry_read import (REGISTRY, HttpStatus, MalformedSource, get,
                               parse, total)
from etl.provenance import write_record

PER_PAGE = 50
ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "sources" / "prerequisite-sweep-measured.json"

#: Where a dying run leaves its progress. Deliberately NOT in `docs/` — it is
#: scratch, it is rewritten hundreds of times, and it must never be mistaken
#: for a published record. `data/` is gitignored.
CHECKPOINT = ROOT / "data" / "prerequisite-sweep-progress.json"

RECORD_NOTE = ("Measured by `python -m etl.sweep_prerequisites`. A census of "
               "every published Registry course, not a sample. `complete` "
               "false means a prefix was read and no rate may be quoted.")

#: How many prose examples and publishers to keep. The sweep sees ~48k courses;
#: keeping every example would make the record a copy of the Registry.
MAX_EXAMPLES = 12


class Progress:
    """The running totals, and the pages they came from.

    A dict would do. A class earns its place by making `pages_read` the only
    way to know how far the walk got — the figure that decides whether a rate
    may be quoted at all cannot then be set from anywhere else.
    """

    def __init__(self, state: dict | None = None) -> None:
        state = state or {}
        self.pages_read: list[int] = list(state.get("pages_read", []))
        self.courses: int = state.get("courses", 0)
        self.states: int = state.get("states", 0)
        self.resolves: int = state.get("resolves", 0)
        self.empty: int = state.get("empty", 0)
        self.typed: int = state.get("typed", 0)
        self.examples: list[str] = list(state.get("examples", []))
        #: publisher -> how many of its courses use the typed edge. The whole
        #: point of #58 if the count is not zero, and useless afterwards if the
        #: sweep only counted.
        self.typed_by_publisher: dict[str, int] = dict(
            state.get("typed_by_publisher", {}))

    def add(self, page: int, envelopes: list) -> None:
        for envelope in envelopes:
            for node in courses_in(envelope):
                said = classify(node)
                self.courses += 1
                self.states += said["states"]
                self.resolves += said["resolves"]
                self.empty += said["empty"]
                if said["uses_typed_edge"]:
                    self.typed += 1
                    who = publisher_of(envelope)
                    self.typed_by_publisher[who] = (
                        self.typed_by_publisher.get(who, 0) + 1)
                for line in said["prose"]:
                    if len(self.examples) < MAX_EXAMPLES:
                        self.examples.append(line[:90])
        self.pages_read.append(page)

    def as_dict(self) -> dict:
        return {"pages_read": self.pages_read, "courses": self.courses,
                "states": self.states, "resolves": self.resolves,
                "empty": self.empty, "typed": self.typed,
                "examples": self.examples,
                "typed_by_publisher": self.typed_by_publisher}


def save(progress: Progress, pages: int) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    # Written whole to a temporary path and moved, so a kill mid-write leaves
    # the previous checkpoint rather than a truncated one. A resume reading
    # half a JSON file is worse than no resume at all.
    scratch = CHECKPOINT.with_suffix(".part")
    scratch.write_text(json.dumps({**progress.as_dict(), "pages": pages},
                                  indent=2), encoding="utf-8")
    scratch.replace(CHECKPOINT)


def load() -> tuple[Progress, int | None]:
    if not CHECKPOINT.exists():
        return Progress(), None
    state = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return Progress(state), state.get("pages")


def page_count(population: int) -> int:
    return -(-population // PER_PAGE)


def sweep(pages: int | None = None, resume: bool = False,
          delay: float = 0.0, quiet: bool = False) -> dict:
    population = total("/ce-registry/course/search")
    if not isinstance(population, int):
        raise RuntimeError(f"the Registry did not report a population: "
                           f"{population}")
    planned = pages or page_count(population)

    progress, previous = load() if resume else (Progress(), None)
    if resume and previous is not None and previous != planned:
        # The corpus grew or the plan changed, so the partial totals are of a
        # different population. Continuing would blend two runs into one figure.
        raise ValueError(
            f"the checkpoint covers a {previous}-page plan and this run wants "
            f"{planned}. Delete {CHECKPOINT.name} and start again rather than "
            f"blending two populations into one rate.")

    done = set(progress.pages_read)
    started = time.monotonic()
    for page in range(1, planned + 1):
        if page in done:
            continue
        body = parse(get(f"{REGISTRY}/ce-registry/course/search"
                         f"?per_page={PER_PAGE}&page={page}"),
                     f"page {page} of the course search")
        if not isinstance(body, list):
            raise MalformedSource(
                f"page {page} of the course search returned "
                f"{type(body).__name__}, not a list of envelopes")
        progress.add(page, body)
        save(progress, planned)
        if not quiet and page % 25 == 0:
            print(f"  page {page}/{planned} · {progress.courses} courses · "
                  f"{progress.typed} typed", flush=True)
        if delay:
            time.sleep(delay)

    result = shape(progress, population, planned, time.monotonic() - started)
    if not quiet:
        report(result)
    return result


def shape(progress: Progress, population: int, planned: int,
          elapsed: float) -> dict:
    read = len(set(progress.pages_read))
    return {
        "population_reported": population,
        "pages_planned": planned,
        "pages_in_population": page_count(population),
        "pages_read": read,
        # The gate everything else is read through, and it is measured against
        # the POPULATION rather than against the plan. Against the plan,
        # `--pages 20` finishes its twenty pages and reports a census — which
        # is precisely the failure this module exists to prevent, arriving
        # through the flag added to make testing cheap.
        "complete": read >= page_count(population),
        "elapsed_seconds": round(elapsed, 1),
        "courses": progress.courses,
        "stating_a_prerequisite": progress.states,
        "resolvable": progress.resolves,
        "free_text_only": progress.states - progress.resolves,
        "stated_but_empty": progress.empty,
        "using_the_typed_edge": progress.typed,
        "typed_edge_publishers": dict(sorted(
            progress.typed_by_publisher.items(),
            key=lambda kv: -kv[1])),
        "examples": progress.examples[:MAX_EXAMPLES],
    }


def report(result: dict) -> None:
    read, planned = result["pages_read"], result["pages_planned"]
    if not result["complete"]:
        # No rate, deliberately. An incomplete sweep has measured a prefix of
        # the Registry, and printing "0 of 31,402" beside a target of 47,862
        # invites the reader to treat it as the answer.
        print(f"INCOMPLETE — {read} of "
              f"{result['pages_in_population']} pages read, "
              f"{result['courses']} courses.\n"
              f"No rate is reported: a prefix is not a census. "
              f"Re-run with --resume.")
        return
    print(f"Swept {result['courses']} courses over {planned} pages "
          f"in {result['elapsed_seconds'] / 60:.1f} min.\n")
    print(f"  stating a prerequisite  {result['stating_a_prerequisite']:>7}")
    print(f"  ...resolvable           {result['resolvable']:>7}")
    print(f"  ...free text only       {result['free_text_only']:>7}")
    print(f"  stated but empty        {result['stated_but_empty']:>7}")
    print(f"\n  using ceterms:prerequisite  {result['using_the_typed_edge']}")
    for who, count in result["typed_edge_publishers"].items():
        print(f"      {count:>5}  {who}")


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(
        prog="python -m etl.sweep_prerequisites",
        description=summary[0] if summary else None)
    parser.add_argument("--pages", type=int, default=None,
                        help="Read only the first N pages (testing).")
    parser.add_argument("--resume", action="store_true",
                        help="Continue from the checkpoint instead of "
                             "re-walking pages already read.")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Seconds to wait between pages (default 0 — the "
                             "Registry is already the rate limiter).")
    parser.add_argument("--json", action="store_true",
                        help="Print the result as JSON.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = sweep(pages=args.pages, resume=args.resume, delay=args.delay,
                       quiet=args.json or args.record)
    except ValueError as refused:
        print(f"\nrefused: {refused}", file=sys.stderr)
        return 1
    except MalformedSource as bad:
        print(f"\nsource malformed: {bad}", file=sys.stderr)
        return 3
    except (HttpStatus, RuntimeError) as gone:
        print(f"\nsource unreachable: {gone}", file=sys.stderr)
        return 2

    if args.record:
        if not result["complete"]:
            # The one thing this module exists to prevent. A partial record on
            # disk outlives the run that made it, and the next reader has no
            # way to know the sweep died.
            print("\nrefused: will not record an incomplete sweep — "
                  f"{result['pages_read']} of "
                  f"{result['pages_in_population']} pages. "
                  "Finish it with --resume.", file=sys.stderr)
            return 1
        write_record(RECORD, {"_": RECORD_NOTE,
                              "retrieved_at": datetime.date.today().isoformat(),
                              **result})
        # `relative_to` raises when the record is written outside the repo,
        # which happens under test and would turn a successful write into a
        # traceback AFTER the file landed — a command that worked, reporting
        # that it did not.
        try:
            where = RECORD.relative_to(ROOT)
        except ValueError:
            where = RECORD
        print(f"wrote {where}")
    elif args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
