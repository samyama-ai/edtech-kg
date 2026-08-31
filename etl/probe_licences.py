"""Read the O*NET and Urban Institute licence positions, and record them.

    python -m etl.probe_licences              # the positions, as prose
    python -m etl.probe_licences --json       # machine-readable
    python -m etl.probe_licences --record     # refresh the committed record

edtech-kg#13 and #14 both ask the same thing of different publishers: locate
the terms, quote them rather than paraphrase, and say what attribution is
owed. Neither is answerable from a summary, so every field this prints is a
span lifted out of the page it came from.

The committed record at `docs/sources/licences-measured.json` is what the doc
tests check the page against. It exists for the reason the SCED one does: a
test that re-reads three websites on every run is a test that fetches from
three publishers on every push, and `conftest.py` refuses that traffic.
Re-read the live pages by running this, which is a decision somebody makes.
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

from etl.licence_positions import (MalformedSource, ONET_CROSSWALKS,
                                   ONET_DATABASE, URBAN_PORTAL, onet_crosswalks,
                                   onet_database, page_text, urban_portal)

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "licences-measured.json"

#: Written INTO the record by `--record`, not left in the file for a refresh
#: to delete. See `main`.
RECORD_NOTE = (
    "One measured run, committed so the page can be checked without reaching "
    "three publishers. Refresh with `python -m etl.probe_licences --record`, "
    "and update the \"read on\" date on licences.md to match.")


def read_all() -> dict:
    """All three positions, each from the page that states it."""
    return {
        "onet_database": onet_database(page_text(ONET_DATABASE)),
        "onet_crosswalks": onet_crosswalks(page_text(ONET_CROSSWALKS)),
        "urban_portal": urban_portal(page_text(URBAN_PORTAL)),
    }


def probe(quiet: bool = False) -> dict:
    stamp = datetime.date.today().isoformat()
    positions = read_all()
    if not quiet:
        database = positions["onet_database"]
        crosswalks = positions["onet_crosswalks"]
        urban = positions["urban_portal"]

        print(f"\nO*NET {database['version']} Database — {ONET_DATABASE}\n")
        print(f"  licence      {database['licence']}")
        print(f"  attribution  {database['attribution']}")
        print(f"  exception    {database['applies_only_to']}")
        # DERIVED, not asserted. This line was hardcoded — it said the
        # crosswalks page is absent from the exception list whether or not it
        # was, on the one claim this whole document turns on. If O*NET ever
        # adds the page, the old line went on printing the opposite.
        #
        # READ, not re-derived. It then computed the boolean a second time
        # from the same string, so the console and the record could disagree
        # about the claim they both exist to state. `licence_positions` records
        # `names_crosswalks_page` precisely so the answer is decided once.
        named = database["names_crosswalks_page"]
        print("               ^ the crosswalks page IS on that list — the "
              "Database licence now covers the workbooks this repo reads"
              if named else
              "               ^ the crosswalks page is NOT on that list")

        # The ONLY ongoing compliance duty either page states, extracted a
        # round ago because the page quoted it with nothing behind it — and
        # then not printed, so someone running the probe to find out what they
        # owe was told everything except the thing they owe.
        print(f"  modification {database['modification']}")

        print(f"\nO*NET crosswalk files — {ONET_CROSSWALKS}\n")
        print(f"  licence      {crosswalks['licence']}")
        print(f"  this repo reads {len(crosswalks['files_this_repo_reads'])} of "
              f"them: {', '.join(crosswalks['files_this_repo_reads'])}")

        print(f"\nUrban Institute Education Data Portal — {URBAN_PORTAL}\n")
        print(f"  licence      {urban['licence']}")
        print(f"  citation     {urban['citation']}")

        print(f"\n  read {stamp}")
        print("  reproduce with: python -m etl.probe_licences\n")

    return {"retrieved_at": stamp, **positions}


def main(argv: list[str] | None = None) -> int:
    summary = (__doc__ or "").splitlines()
    parser = argparse.ArgumentParser(description=summary[0] if summary else None)
    parser.add_argument("--json", action="store_true",
                        help="Print the result as JSON.")
    parser.add_argument("--record", action="store_true",
                        help=f"Write {RECORD.name} from this run.")
    args = parser.parse_args(argv)
    try:
        result = probe(quiet=args.json or args.record)
    except MalformedSource as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    if args.record:
        # `ensure_ascii=False`, as `probe_sced` does. Without it the registered
        # trademark in O*NET's own attribution wording is written to the record
        # as `\u00ae` — a document whose entire subject is reproducing that
        # string exactly, storing it escaped.
        #
        # `_` FIRST, and written by the writer. The committed record opened
        # with a note saying how to refresh it, and this command — the one the
        # note names — did not emit the key, so refreshing the file deleted
        # its own instructions. A record that documents itself has to be
        # documented by the thing that writes it, or the documentation lasts
        # exactly until someone follows it.
        RECORD.write_text(
            json.dumps({"_": RECORD_NOTE, **result}, indent=2,
                       ensure_ascii=False) + "\n", encoding="utf-8")
        # Derived, not spelled again. The directory was written into the
        # message as a literal, so moving the record would have left the
        # command reporting a path it had not written to.
        #
        # Relative to the REPO, not the cwd — the probe is run from anywhere.
        # And `relative_to` RAISES on a path outside its argument, so the
        # first version of this crashed the moment a test pointed `RECORD`
        # somewhere else: a reporting line that can abort the command it is
        # reporting on. `is_relative_to` first.
        where = (RECORD.relative_to(ROOT) if RECORD.is_relative_to(ROOT)
                 else RECORD)
        print(f"wrote {where}")
    # `if`, not `elif`. `--json --record` accepted both flags and silently
    # printed nothing, so a caller asking for the record AND the output got
    # half of what it asked for with no indication which half.
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
