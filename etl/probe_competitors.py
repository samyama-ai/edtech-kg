"""Who already sells course planning, and what do they say they do.

edtech-kg#47. Sandeep named GT.school, Ellucian and LTS Education in the
2026-08-18 review. The goal it serves is *"a demo that helps their product
roadmap and their customers do something better, faster or cheaper"* — and you
cannot argue "better" without knowing what the current best is.

**This measures what vendors STATE PUBLICLY. It is not a capability
comparison**, and the difference matters: a page that does not mention degree
audit is a page, not a product that lacks one. Every figure here is a term
count and a status code over a page we were allowed to fetch, and the record
says which page.

**Robots first, for every host, before anything else is asked.** That is code
rather than a habit because #41 got the order wrong — the ECS table was
fetched several times before its robots.txt was read, and the gate exists so
that cannot happen again.

**AND ROBOTS IS NOT THE WHOLE OF PERMISSION.** `www.coursicle.com/robots.txt`
carries `Disallow: /` for a list of user-agents that includes `ClaudeBot`,
`anthropic-ai` and `Claude-Web`. This repo's agent string is none of those, so
a parser says we may fetch — and we do not. The publisher's intent is plainly
to exclude automated agents of this kind, and a finding that rested on our
user-agent happening not to appear on their list would be technically
permitted and worth nothing. It is recorded as excluded, with the reason.

    python -m etl.probe_competitors
    python -m etl.probe_competitors --record
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

from etl.identity import USER_AGENT
from etl.probe_graduation import Unreachable, robots_for
from etl.provenance import write_record

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "sources" / "competitors-measured.json"
RECORD_NOTE = (
    "Measured by `python -m etl.probe_competitors --record`. Term counts over "
    "one public page per vendor, robots-checked before the first request. "
    "A vendor recorded as `excluded` was NEVER fetched. These are counts of "
    "what a page says, not an assessment of what a product does — a page that "
    "does not mention degree audit is a page, not a product without one.")

DELAY = 1.5

#: Named in the issue, plus the wider field it asks about. One page each: the
#: product or solutions page, because that is where a vendor states what it
#: sells.
VENDORS = {
    "GT.school": {
        "url": "https://gt.school/",
        "why": "named in the review — gifted-and-talented, outside "
               "conventional schooling, Dev Factory / Crossover umbrella",
    },
    "Ellucian": {
        "url": "https://www.ellucian.com/solutions",
        "why": "named in the review — large US higher-education vendor; "
               "student pathway and degree audit products",
    },
    "LTS Education": {
        "url": "https://ltseducationsystems.com/",
        "why": "named in the review, and recorded as probably defunct — "
               "a dead company's pages are sometimes the clearest statement "
               "of what a market wanted",
    },
    "PowerSchool (Naviance)": {
        # The Naviance product URLs 404 and `naviance.com` answers 200 with
        # 212 bytes — a redirect stub, not a page. The company's own home page
        # is what is actually published, so that is what is measured, and the
        # record says so rather than reporting a 404 as "says nothing".
        "url": "https://www.powerschool.com/",
        "why": "the incumbent in US high-school course planning; Naviance's "
               "own product pages 404 and naviance.com is a 212-byte stub",
    },
    "Stellic": {
        "url": "https://stellic.com/",
        "why": "degree audit and pathway planning, higher education",
    },
    "Civitas Learning": {
        "url": "https://www.civitaslearning.com/",
        "why": "student outcome analytics, higher education",
    },
}

#: Vendors we will not fetch, and why. Kept in the record so the absence is a
#: decision a reader can check rather than a gap.
EXCLUDED = {
    "Coursicle": {
        "url": "https://www.coursicle.com/",
        "why": "robots.txt carries `Disallow: /` for a list of user-agents "
               "including ClaudeBot, anthropic-ai and Claude-Web. This repo's "
               "agent is none of those, so a parser permits the fetch. The "
               "publisher's intent is plainly to exclude automated agents of "
               "this kind, and a finding resting on our user-agent not being "
               "on their list would be technically permitted and worth "
               "nothing. NOT FETCHED.",
    },
}

#: What a page has to say for itself. Counted, not interpreted.
TERMS = ("degree audit", "course plan", "pathway", "prerequisite",
         "graduation requirement", "knowledge graph", "transfer credit",
         "advisor", "api")


def fetch(url: str) -> dict:
    """One page, robots-gated. The gate is INSIDE, so it cannot be skipped."""
    permission = dict(robots_for(url))
    if not permission["allowed"]:
        return {**permission, "url": url, "status": None, "bytes": 0,
                "fetched": False}

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(DELAY)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
            return {**permission, "url": url, "status": response.status,
                    "bytes": len(body), "fetched": True, "body": body}
    except urllib.error.HTTPError as refused:
        # A refusal is a measurement. A vendor that will not answer an
        # identified research agent is a fact about the vendor.
        return {**permission, "url": url, "status": refused.code,
                "bytes": 0, "fetched": False}
    except (urllib.error.URLError, TimeoutError, OSError) as gone:
        raise Unreachable(f"{url}: {gone}") from gone


def readable(markup: str) -> str:
    """Page text, lowercased. Scripts and styles are not what a page says."""
    without = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<!--.*?-->",
                     " ", markup, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", without))).lower()


def measure() -> dict:
    vendors = {}
    for name, about in VENDORS.items():
        try:
            found = fetch(about["url"])
        except Unreachable as gone:
            # **Unreachable is not refused.** A company that has stopped
            # trading and one that blocks us are different facts, and the
            # issue expects one of these to be the first.
            vendors[name] = {"url": about["url"], "why": about["why"],
                             "reachable": False, "note": str(gone)[:200]}
            continue
        body = found.pop("body", "")
        text = readable(body) if body else ""
        vendors[name] = {
            **found, "why": about["why"], "reachable": True,
            # **The READABLE length, beside the byte length.** A page can be
            # 462,822 bytes and carry 8,105 characters of text, and a term
            # count of zero means different things in those two numbers: no
            # text at all is a reader artefact, text without the term is a
            # finding. #181 shipped `bytes: 0` that was an artefact of a
            # discard; this is the same trap one page over.
            "text_chars": len(text),
            "terms": {term: text.count(term) for term in TERMS} if text else {},
            "says_nothing_about_planning": bool(text) and not any(
                text.count(t) for t in
                ("degree audit", "course plan", "pathway", "prerequisite")),
        }
    return {
        "_": RECORD_NOTE,
        "terms_counted": list(TERMS),
        "vendors": vendors,
        "excluded": EXCLUDED,
    }


def report(found: dict) -> None:
    print(f"  {len(found['vendors'])} vendors fetched, "
          f"{len(found['excluded'])} excluded without fetching\n")
    width = max(len(n) for n in found["vendors"])
    for name, v in found["vendors"].items():
        if not v.get("reachable"):
            print(f"  {name:<{width}}  UNREACHABLE — {v['note'][:52]}")
            continue
        if not v.get("fetched"):
            why = "robots" if not v.get("allowed") else f"HTTP {v['status']}"
            print(f"  {name:<{width}}  not fetched — {why}")
            continue
        hits = {t: n for t, n in v["terms"].items() if n}
        print(f"  {name:<{width}}  {v['bytes']:>7,}b "
              f"{v['text_chars']:>6,}ch  "
              f"{', '.join(f'{t} {n}' for t, n in sorted(hits.items())) or 'no terms'}")
    for name, why in found["excluded"].items():
        print(f"\n  {name}: NOT FETCHED — {why['why'][:120]}…")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl.probe_competitors",
        description=__doc__.strip().splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)

    if args.json and args.record:
        print("--json and --record ask for different things; pick one.",
              file=sys.stderr)
        return 2
    found = measure()
    if args.json:
        print(json.dumps(found, indent=2))
        return 0
    report(found)
    if args.record:
        if not any(v.get("fetched") for v in found["vendors"].values()):
            # Nothing answered at all is a network problem, not a finding, and
            # writing it would record the field as silent.
            print("refusing to --record: no vendor page answered.",
                  file=sys.stderr)
            return 3
        write_record(RECORD, found)
        print(f"\n  -> {RECORD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
