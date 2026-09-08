"""Printing a CI-history measurement for a person to read.

Split from `etl/probe_ci_history.py` when it passed the 500-line review limit.
Split by SUBJECT: that module measures, this one presents. The distinction
earns its keep here — the presentation has its own failure, and it happened:
with no diagnostic workflow committed the report printed "0 of 0 diagnostic
steps are continue-on-error", a sentence about a file that does not exist.

edtech-kg#109.
"""

from __future__ import annotations



def report(measured: dict) -> None:
    out = measured["workflows"]
    # Read off the verdict rather than imported, so the report cannot disagree
    # with the record it is printing.
    floor = measured["verdict"]["floor_seconds"]
    print(f"  {measured['runs_returned']} runs returned by the API\n")
    for name in sorted(out):
        seen = out[name]
        uses = measured["dependencies"].get(name, {}).get("count")
        print(f"  {name}")
        print(f"    {seen['runs']} run(s), {seen['success']} success, "
              f"{seen['failure']} failure, {seen['other']} other")
        print(f"    {seen['first']} .. {seen['last']}")
        print(f"    median {seen['median_seconds']}s, max {seen['max_seconds']}s, "
              f"{seen['over_floor']} run(s) over the {floor}s floor")
        print(f"    uses: {uses if uses is not None else 'not committed here'}")
        print()

    check = measured["verdict"]
    with_actions, without = check["with_actions"], check["without_actions"]
    if with_actions and without:
        print(f"  With actions ({', '.join(with_actions['uses']) or 'none'}): "
              f"{with_actions['success']}/{with_actions['runs']} succeeded, "
              f"{with_actions['failure']} failed")
        print(f"  Without actions "
              f"({', '.join(without['workflows'])}): "
              f"{without['success']}/{without['runs']} succeeded, "
              f"{without['failure']} failed")
    if check["in_history_but_not_committed"]:
        print(f"  ran but not committed, so unclassifiable from the tree: "
              f"{', '.join(check['in_history_but_not_committed'])}")
    # Only when there IS a diagnostic. With the workflow deleted this printed
    # "0 of 0 diagnostic steps are continue-on-error" — a sentence about a
    # file that does not exist.
    if not check["diagnostic_steps"]:
        print("\n  NOTE: no runner-diagnostic.yml is committed, so nothing "
              "here isolates fetching an action as the variable.")
    elif not check["diagnostic_outcome_is_informative"]:
        print(f"\n  NOTE: {check['diagnostic_tolerant_steps']} of "
              f"{check['diagnostic_steps']} diagnostic steps are "
              f"continue-on-error, so its SUCCESS means the job ran — not "
              f"that anything it probed worked. That answer is in the log.")
