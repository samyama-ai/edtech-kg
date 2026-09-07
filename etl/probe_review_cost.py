"""What a PR's size costs in review rounds — edtech-kg#26.

`CONTRIBUTING.md` states a size rule, and a rule about PR size is worth exactly
as much as the evidence behind it. This produces that evidence: every merged
PR, its insertions, and how many `REQUEST_CHANGES` reviews it took.

    python -m etl.probe_review_cost
    python -m etl.probe_review_cost --record

**Not run by the suite, and that is the point.** It needs a Gitea token and it
makes one API call per merged PR, so the committed record is what the tests
check the page against — which is the same rule the page itself states for
every other figure in this repo.

Insertions come from the MERGE COMMIT rather than the API's `additions`, which
the list endpoint does not carry. `--first-parent` on the merge is the change
the PR actually brought onto main, not the union of both sides.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

from etl.identity import USER_AGENT
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "review-cost-measured.json"
API = "https://git.samyama.ai/api/v1/repos/Samyama.ai/edtech-kg"

#: Written INTO the record by `--record`, as the sibling probes do.
RECORD_NOTE = (
    "One measured run of `python -m etl.probe_review_cost --record`, committed "
    "so the size table in CONTRIBUTING.md can be checked without a token and "
    "without one API call per merged PR.")

#: The bands the page reports. Boundaries here, not in the page, so the two
#: cannot disagree about where a band starts.
BANDS = ((250, "under 250"), (700, "250-700"), (1500, "700-1500"),
         (None, "over 1500"))


class Unreachable(Exception):
    """The forge did not answer. Reported, never silently skipped — a partial
    walk would report a size table drawn from whichever PRs happened to load."""


def token() -> str:
    for name in ("GITEA_TOKEN", "SAMYAMA_GITEA_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    raise Unreachable(
        "no Gitea token in GITEA_TOKEN or SAMYAMA_GITEA_TOKEN. This probe "
        "reads a private forge; the committed record is what the tests use.")


def get(path: str, attempts: int = 4):
    request = urllib.request.Request(
        f"{API}{path}", headers={"Authorization": f"token {token()}",
                                 "User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        # FIRST, because `HTTPError` subclasses `URLError`. A 401 from a bad
        # token burned four attempts with backoff and then reported that the
        # forge "did not answer" — the wrong diagnosis for the failure a reader
        # is most likely to hit, arrived at slowly.
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise Unreachable(
                    f"{path} answered HTTP {exc.code} ({exc.reason}). A 401 is "
                    f"a token problem and a 404 is a PR this token cannot see; "
                    f"neither is worth retrying.") from exc
            if attempt == attempts - 1:
                raise Unreachable(f"{path} answered HTTP {exc.code}") from exc
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == attempts - 1:
                raise Unreachable(f"{path} did not answer ({exc})") from exc
            time.sleep(1.5 * (attempt + 1))
    raise Unreachable(f"{path} did not answer")


def band(insertions: int) -> str:
    for ceiling, name in BANDS:
        if ceiling is None or insertions < ceiling:
            return name
    raise AssertionError("BANDS must end in an open band")


def merged_sizes() -> tuple[dict[int, int], list[str]]:
    """PR number to insertions, read from the merge commits on main.

    Returns what was skipped as well. A PARTIALLY dropped walk produces a table
    that looks complete and is not — the same failure the refusal below exists
    to prevent, arrived at quietly instead of loudly.
    """
    log = subprocess.run(
        ["git", "log", "--merges", "--format=%H%x09%s", "origin/main"],
        capture_output=True, text=True, cwd=ROOT, check=True).stdout.splitlines()
    sizes, skipped = {}, []
    for line in log:
        sha, _, subject = line.partition("\t")
        # ANCHORED to the merge-subject form, not the first `#N` in the line.
        # `Merge pull request '<title>' (#N) from <branch>` — and this repo's
        # titles reference issues in prose routinely, this probe's own
        # docstring included. The first such title would have attributed
        # another PR's review rounds to it, silently, and the table would still
        # have looked right.
        found = re.search(r"\(#(\d+)\) from ", subject)
        if not found:
            skipped.append(f"{sha[:9]} names no PR: {subject[:56]}")
            continue
        stat = subprocess.run(
            ["git", "show", "--shortstat", "--format=", "-m", "--first-parent", sha],
            capture_output=True, text=True, cwd=ROOT, check=True).stdout
        insertions = re.search(r"(\d+) insertion", stat)
        if insertions:
            sizes[int(found.group(1))] = int(insertions.group(1))
        else:
            skipped.append(f"#{found.group(1)} has no insertions in its merge")
    return sizes, skipped


def rounds(number: int) -> int:
    return sum(1 for r in get(f"/pulls/{number}/reviews")
               if r["state"] == "REQUEST_CHANGES")


def probe(quiet: bool = False) -> dict:
    sizes, skipped = merged_sizes()
    if not sizes:
        raise Unreachable(
            "no merge commits on origin/main name a PR — a table built from "
            "this would report zero PRs as evidence for a rule")

    tally: dict[str, list[int]] = {name: [] for _, name in BANDS}
    for number, insertions in sorted(sizes.items()):
        tally[band(insertions)].append(rounds(number))

    table = {name: {"prs": len(v),
                    "mean_rounds": round(sum(v) / len(v), 1),
                    "worst": max(v)}
             for name, v in tally.items() if v}
    result = {"pull_requests": len(sizes), "bands": table,
              # Reported, not swallowed. A silent partial walk is a table that
              # looks complete; the count is on the page so a reader can see
              # what the figures rest on.
              "merges_skipped": len(skipped), "skipped": skipped,
              "read_or_measured": "measured"}

    if not quiet:
        print("\nWhat a PR's size costs in review — edtech-kg#26\n")
        print(f"  {len(sizes)} merged PRs matched to a size", end="")
        print(f", {len(skipped)} merges skipped\n" if skipped else "\n")
        print(f"  {'insertions':<12} {'PRs':>4} {'mean rounds':>12} {'worst':>6}")
        for name, row in table.items():
            print(f"  {name:<12} {row['prs']:>4} {row['mean_rounds']:>12.1f} "
                  f"{row['worst']:>6}")
        print()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json or args.record)
    except Unreachable as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.record:
        write_record(RECORD, {"_": RECORD_NOTE, **result})
        print(f"wrote {RECORD.relative_to(ROOT)}")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
