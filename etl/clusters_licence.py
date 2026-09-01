"""Reading the Career Clusters licence off two published pages.

Split from `etl/probe_codesets.py` when that file passed the 500-line review
limit, on the line its own docstring already draws: three things there are
MEASURED, and this one is READ. A licence position is a fact about a document.

The distinction is load-bearing. A measurement that comes back wrong is a
wrong number; a licence position that comes back wrong from a page nobody
could read is a statement about what this project may legally use. Both pages
that feed it are guarded, and the blocker that reached review was guarding
only one of them.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from etl.identity import USER_AGENT


class MalformedSource(Exception):
    """A source that answered, but not with what it publishes.

    Defined HERE, in the half that imports no sibling, and re-exported by
    `probe_codesets` — both raise the one exception and `main()` catches it
    once. Putting it in the half that imports this one is a cycle.
    """


CLUSTERS = "https://careertech.org/career-clusters/"
CLUSTER_CROSSWALKS = "https://careertech.org/crosswalks/"


def page_text(url: str) -> str:
    """One page, or a refusal naming it."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MalformedSource(f"{url} did not answer ({exc})") from exc


def links_to(page: str, *extensions: str) -> list[tuple[str, str]]:
    """Every `href` on this page ending in one of these extensions.

    ONE pattern, three callers — `data_files`, the PDF scan and the crosswalks
    load guard each carried their own and diverged twice, and the guard is the
    one that decides whether the page loaded at all.

    The opening quote is BACKREFERENCED, so `href="a.csv'` is not a link and a
    double-quoted href holding an apostrophe is. A query string or fragment may
    follow the extension, since `/x.xlsx?v=2` is a real link and a missed one
    is the false zero that manufactures the licence conclusion.

    Returns `(href, path)`: as written, and with query and fragment removed.
    """
    alternatives = "|".join(re.escape(e) for e in extensions)
    pattern = (r"""href=(["'])((?:(?!\1)[^\s>])*\.(?:""" + alternatives + r"""))"""
               r"""((?:[?#](?:(?!\1)[^\s>])*)?)\1""")
    return [(quote + path + tail, path)
            for quote, path, tail in re.findall(pattern, page, re.I)]


def data_files(page: str) -> list[str]:
    """Paths to a machine-readable data file on one page.

    Zero here feeds the licence conclusion, so a link this misses is worse
    than one it counts twice — `links_to` carries the two rules that make
    that true.
    """
    return sorted({path for _, path in
                   links_to(page, "xlsx", "xls", "csv", "json")})


def career_clusters() -> dict:
    """Read rather than measured — the licence question edtech-kg#35 asks.

    Everything here is quoted from the page as it stood on the retrieval date,
    because a licence position is a fact about a document and not about data.

    Deliberately not cached on disk, unlike the two workbooks: a licence
    position is exactly the thing that should be re-read rather than served
    from a copy taken months ago. The cost is one request per run.
    """
    page = page_text(CLUSTERS)
    crosswalks = page_text(CLUSTER_CROSSWALKS)
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    # Periods allowed: the notice reads "© 2023 Advance CTE: State Leaders
    # Connecting Learning to Work. All rights reserved.", and stopping at the
    # first full stop reported no notice on a page that carries one.
    notice = re.search(r"(©\s*\d{4}[^©]{0,160}?All rights reserved)", flat)
    structure = re.search(r"(\d+) Clusters and (\d+) Sub-Clusters", flat)
    # REFUSED when the page carries neither landmark. A redirect, a cookie
    # wall or a script shell answers 200 with no content, and every field then
    # comes back None or empty — the same zero `docs/sources/code-sets.md`
    # rests its "NOT cleared" position on. A licence conclusion is the last
    # thing that should rest on a number with two meanings.
    #
    # BOTH must be missing, not either: Advance CTE can reword a copyright
    # line without the page having failed, and refusing on one would turn an
    # ordinary edit into a broken probe.
    if notice is None and structure is None:
        raise MalformedSource(
            f"{CLUSTERS} carried neither the copyright notice nor the "
            f"'N Clusters and M Sub-Clusters' line ({len(flat)} characters of "
            f"text). Both are on the page this probe reads, so their joint "
            f"absence means what came back is not that page — a redirect, a "
            f"cookie wall or a script shell. Refusing rather than reporting "
            f"the zero it would otherwise produce, because that zero is what "
            f"the licence position is argued from.")

    # The crosswalks page too, and SECOND. Both feed the conclusion — this one
    # carries the PDF count and the crosswalks-page zero — so guarding one of
    # two is not guarding the conclusion. Second because both can fail and only
    # one message shows: the framework page holds what the licence is read
    # from, so its failure is the one to name.
    #
    # It has no cluster count and no copyright line, so it is checked on what
    # it does carry: links to published files, through the same `links_to` the
    # counters use.
    if not links_to(crosswalks, "pdf", "xlsx", "xls", "csv", "json",
                    "doc", "docx"):
        raise MalformedSource(
            f"{CLUSTER_CROSSWALKS} carried no links to published files at all "
            f"({len(crosswalks)} characters). That page is where the PDF count "
            f"and the crosswalks-page zero both come from, so a failed load "
            f"there produces the same numbers as a genuine absence — and the "
            f"licence position is argued from exactly those numbers.")

    machine_readable = data_files(page)
    on_crosswalks = data_files(crosswalks)
    return {"source": CLUSTERS,
            "crosswalks_source": CLUSTER_CROSSWALKS,
            "copyright_notice": notice.group(1).strip() if notice else None,
            "clusters": int(structure.group(1)) if structure else None,
            "sub_clusters": int(structure.group(2)) if structure else None,
            # Per page. The conclusion rests on the crosswalks page, so the
            # count from that page is the one the document quotes.
            "machine_readable_files": machine_readable,
            "machine_readable_on_crosswalks": on_crosswalks,
            # What IS published there — the corroboration, counted rather
            # than described, through the same `links_to` as the zero beside
            # it so the two cannot disagree about what a link is.
            "pdfs_on_crosswalks": sorted({
                path.rsplit("/", 1)[-1]
                for _, path in links_to(crosswalks, "pdf")}),
            "measured_or_read": "read"}
