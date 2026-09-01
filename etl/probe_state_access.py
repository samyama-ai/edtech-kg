"""Measure which state education departments answer a machine — #50.

    python -m etl.probe_state_access             # the table
    python -m etl.probe_state_access --json      # machine-readable
    python -m etl.probe_state_access --record    # refresh the committed record

Ten requests: a homepage and a robots.txt for each of five departments. That
is the whole cost, and it is why this is not cached — the point is what the
sites do TODAY, and a block that has been lifted is exactly the thing a stale
copy would hide.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib

from etl.state_access import recommendation, survey

RECORD = pathlib.Path(__file__).resolve().parents[1] / "docs" / "sources" / \
    "state-access-measured.json"


def probe(quiet: bool = False) -> dict:
    results = survey()
    result = {"retrieved_at": datetime.date.today().isoformat(),
              "departments": {name: {**one, "recommendation": recommendation(one)}
                              for name, one in results.items()}}
    if not quiet:
        print("\nState education departments — what answers a machine\n")
        print(f"  {'department':<30} {'homepage':<16} {'robots.txt':<16} verdict")
        for name, one in result["departments"].items():
            print(f"  {name:<30} {one['homepage']['outcome']:<16} "
                  f"{one['robots_txt']['outcome']:<16} {one['recommendation']}")
        blocked = [n for n, o in result["departments"].items()
                   if o["robots_txt"]["outcome"] == "refused"]
        print(f"\n  {len(blocked)} refuse robots.txt itself — the file that exists "
              f"to be read by a machine.")
        print("  A refusal there is not a crawler policy. It is a refusal before "
              "any policy is consulted,")
        print("  so there is no user-agent to negotiate with.")
        print(f"\n  measured {result['retrieved_at']}")
        print("  reproduce with: python -m etl.probe_state_access\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    result = probe(quiet=args.json or args.record)
    if args.record:
        RECORD.write_text(json.dumps(result, indent=2) + "\n")
        print(f"wrote docs/sources/{RECORD.name}")
    elif args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
