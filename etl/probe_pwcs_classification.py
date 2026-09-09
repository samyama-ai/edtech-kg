"""What `classify` says about every cached PWCS page, recorded.

edtech-kg#19. `tests/test_course_page_against_pwcs.py` is the strongest guard
on the classifier — it runs it over 961 real pages and cross-checks against
`etl/probe_pwcs.py`'s independently written pattern. It is also **cache-gated,
and `data/` is gitignored**, so in a fresh clone all three of its tests skip
and the suite reports green.

That is the problem this record exists for. The claim "961 cached PWCS pages,
0 classified differently" rested on a corpus nobody else has, in the test most
likely to catch a reader regression — and it did not catch two of them.

So the classification is committed, and the markup is not. **The pages are the
district's text and this repo does not republish it**: what is stored per page
is the path, a hash of the markup, and what `classify` answered. That is
enough for a regression test where the cache exists, and enough for a reader
without one to see the shape of the corpus the page's claims rest on.

    python -m etl.probe_pwcs_classification --record
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import pathlib
import sys
import urllib.parse

from etl.course_page import classify
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "pwcs"
BASE = "https://catalog.pwcs.edu"
RECORD = ROOT / "docs" / "sources" / "pwcs-classification-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.probe_pwcs_classification --record` over the "
    "cached PWCS corpus. Per page: the path, a sha256 of the markup, and what "
    "`etl.course_page.classify` answered. The MARKUP IS NOT STORED — it is "
    "the district's course text and this repo does not republish it. The "
    "hash is what lets a later run say whether a classification changed "
    "because the reader changed or because the page did. "
    "A DIGEST, not a row per page: 961 rows is ten times this repo's "
    "500-line review limit, and a record nobody reads is not a record. It "
    "localises nothing by design — where the cache exists the sibling tests "
    "name the page, and where it does not, what a reader needs is whether "
    "the claim still holds.")


def corpus() -> dict[str, str]:
    pages = {}
    for cached in sorted(CACHE.iterdir()):
        url = urllib.parse.unquote(
            cached.name[:-5] if cached.name.endswith(".html") else cached.name)
        path = url[len(BASE):] if url.startswith(BASE) else url
        pages[path] = cached.read_text(encoding="utf-8", errors="replace")
    return pages


def measure() -> dict:
    pages = corpus()
    published = set(pages)
    kinds = collections.Counter()
    by_kind: dict[str, list[str]] = collections.defaultdict(list)
    every = hashlib.sha256()
    for path, markup in sorted(pages.items()):
        found = classify(markup, published, BASE)
        kinds[found["kind"]] += 1
        line = (f"{path}\t{hashlib.sha256(markup.encode()).hexdigest()}\t"
                f"{found['kind']}\t{','.join(found.get('links') or [])}")
        every.update(line.encode())
        by_kind[found["kind"]].append(line)
    return {
        "_": RECORD_NOTE,
        "base": BASE,
        "pages": len(pages),
        "kinds": dict(kinds),
        # **Zero is the figure to watch.** An `unbounded field` anywhere means
        # the reader met markup it could not stand behind; none in the whole
        # corpus was read for a round as evidence it had stayed in bounds,
        # when it also happens when the ceiling silently swallows a field.
        "unbounded": kinds.get("unbounded field", 0),
        # One digest over every page's (path, markup hash, kind, links), and
        # one per kind so a drift says WHICH answer moved without a row per
        # page.
        "digest": every.hexdigest(),
        "digest_by_kind": {
            kind: hashlib.sha256("".join(lines).encode()).hexdigest()
            for kind, lines in sorted(by_kind.items())},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_pwcs_classification",
        description=__doc__.strip().splitlines()[0])
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if not CACHE.exists():
        print(f"{CACHE.relative_to(ROOT)} is not here — `data/` is gitignored. "
              f"Run the PWCS probe first.", file=sys.stderr)
        return 2
    found = measure()
    print(f"  {found['pages']:,} cached pages")
    for kind, n in sorted(found["kinds"].items(), key=lambda kv: -kv[1]):
        print(f"    {n:>5,}  {kind}")
    if args.record:
        if not found["pages"]:
            print("refusing to --record: the corpus is empty.", file=sys.stderr)
            return 3
        write_record(RECORD, found)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
