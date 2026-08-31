"""Reading the O*NET and Urban Institute licence positions off their own pages.

READ, not measured — the distinction `etl/clusters_licence.py` draws and the
same one applies here. A wrong measurement is a wrong number; a wrong licence
position is a statement about what this project may lawfully publish.

Three pages rather than two, and that is the finding. The O*NET **Database**
content licence carries an exception list, and the crosswalks page is not on
it, so the licence that covers the database does not cover the two crosswalk
workbooks this repo actually reads. Those are cleared by a notice of their own
on the page that publishes them. Quoting the database licence at them would be
citing a document that excludes them by name.

Deliberately uncached, like `career_clusters()`: a licence position is exactly
the thing that should be re-read rather than served from a copy taken months
ago. The cost is three requests per run, and no test makes them — every reader
here takes page text, so the suite hands it fixtures directly.
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request


class MalformedSource(Exception):
    """A page that answered, but not with what it publishes."""


class Unreachable(MalformedSource):
    """The page could not be fetched at all.

    A SUBCLASS, so every existing `except MalformedSource` still catches it and
    the CLI keeps mapping both to one exit code. But the two are different
    facts: "the licence sentence is missing" is a finding about the document,
    "the host did not answer" is a finding about the network, and reporting a
    timeout in the words of the first invites someone to conclude the
    publisher changed their terms.
    """


USER_AGENT = "edtech-kg research (+https://git.samyama.ai/Samyama.ai/edtech-kg)"

ONET_DATABASE = "https://www.onetcenter.org/license_db.html"
ONET_CROSSWALKS = "https://www.onetcenter.org/crosswalks.html"
URBAN_PORTAL = "https://educationdata.urban.org/documentation/"


def page_text(url: str) -> str:
    """One page, or a refusal naming it.

    `OSError` alone. `URLError` and `TimeoutError` are both subclasses of it,
    so the three-item tuple caught nothing the one does and read as though it
    covered more.

    The charset comes from the RESPONSE, not from an assumption. These are
    three third-party pages this repo does not control; O*NET serves UTF-8
    today, and a publisher moving to Latin-1 would have turned every accented
    character into a replacement character inside a sentence being quoted
    VERBATIM as a licence position. `errors="replace"` stays as the last
    resort, so a mis-declared charset still yields readable text rather than
    an exception.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except OSError as exc:
        raise Unreachable(f"{url} did not answer ({exc})") from exc
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        # A charset name Python does not know. Named rather than swallowed:
        # falling back silently is how a page gets quoted through the wrong
        # codec and nobody finds out.
        return body.decode("utf-8", errors="replace")


def flatten(page: str) -> str:
    """Tags out, whitespace squashed to single spaces.

    Every reader below works on this rather than on raw HTML, because the
    sentences being quoted are broken across tags and newlines on all three
    pages, and a pattern written against the rendered text is the one a human
    can check against what they see in a browser.

    ORDER MATTERS, and getting it wrong is silent. Scripts go first: strip the
    tags first and a page's inline JavaScript survives as prose, which on the
    O*NET page is most of what is left. Entities go LAST, after the tags, so
    `O*NET&reg;` becomes `O*NET\u00ae` and the version pattern can reach the
    number behind it — the first version of this refused a page it had loaded
    perfectly well.
    """
    without_code = re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", without_code))).strip()


def _one(pattern: str, text: str, url: str, what: str) -> str:
    """One match, or a refusal that names the page and what was sought.

    Shared by all three readers. The failure it exists to prevent is the same
    one `clusters_licence` refuses on: a redirect, a cookie wall or a script
    shell answers 200 with no content, every field comes back None, and a
    licence position gets argued from an absence that means nothing.
    """
    found = re.search(pattern, text, re.I)
    if found is None:
        raise MalformedSource(
            f"{url} did not carry {what} ({len(text)} characters of text). "
            f"That sentence is the licence position, so its absence is not a "
            f"weaker answer — it means what came back is not this page. "
            f"Refusing rather than recording a blank.")
    return re.sub(r"\s+", " ", found.group(1)).strip()


def onet_database(page: str) -> dict:
    """The O*NET Database content licence, and the pages it excludes.

    `applies_only_to` is quoted because it is the load-bearing sentence. The
    licence is CC BY 4.0 and it is easy to stop reading there; the next line
    says which downloads it covers, and the crosswalks page is absent from it.
    """
    text = flatten(page)
    return {
        "source": ONET_DATABASE,
        "version": _one(r"O\*NET.{0,3} (\d+\.\d+) Database Content License",
                        text, ONET_DATABASE, "a database version number"),
        "licence": _one(
            r"(Except as noted below, the content of the O\*NET [\d.]+ Database "
            r"is licensed under a Creative Commons Attribution 4\.0 "
            r"International License)",
            text, ONET_DATABASE, "the Creative Commons licence sentence"),
        "attribution": _one(
            r"(This page includes information from the O\*NET [\d.]+ Database by "
            r"the U\.S\. Department of Labor.{0,120}?trademark of USDOL/ETA\.)",
            text, ONET_DATABASE, "the verbatim attribution wording"),
        "applies_only_to": _one(
            r"(This license applies only to downloadable files on the following "
            r"pages:.{0,120}?)To copy or adapt",
            text, ONET_DATABASE, "the exception list"),
        "read_or_measured": "read",
    }


# The two workbooks this repo actually reads, as O*NET titles them on the
# crosswalks page. "Classfication" is their spelling and is left alone.
CROSSWALK_FILES = ("Classfication of Instructional Programs (CIP)",
                   "Registered Apprenticeship Partners Information Data System "
                   "(RAPIDS)")


def _files_on(text: str) -> list[str]:
    """Which of our two workbooks this page still publishes.

    REFUSES on none. The module's own docstring says a licence position that
    comes back wrong from a page nobody could read is a statement about what
    this project may lawfully use — and an empty list here says exactly that
    while looking like an ordinary result. If O*NET moves both workbooks, the
    page's clearance stops covering what this repo reads, and that has to
    surface as a refusal rather than as a quiet zero.

    One of two is not a refusal: a publisher may rename or retire a single
    file, and the caller records which survived.
    """
    found = [name for name in CROSSWALK_FILES if name in text]
    if not found:
        raise MalformedSource(
            f"{ONET_CROSSWALKS} named neither workbook this repo reads "
            f"({len(text)} characters of text). The licence notice on that "
            f"page is what clears these two files; a page carrying the notice "
            f"and neither file does not clear them. Refusing rather than "
            f"returning an empty list, which reads as an ordinary result.")
    return found


def onet_crosswalks(page: str) -> dict:
    """The notice on the page that publishes the two workbooks this repo reads.

    Its own footer, not the database licence — see the module docstring. The
    file names are carried so the claim is anchored to the downloads it is
    being made about, including the publisher's spelling of "Classfication",
    which is theirs and is left alone.
    """
    text = flatten(page)
    return {
        "source": ONET_CROSSWALKS,
        "licence": _one(
            r"(Crosswalk Files by U\.S\. Department of Labor.{0,120}?licensed "
            r"under a Creative Commons Attribution 4\.0 International License)",
            text, ONET_CROSSWALKS, "the crosswalk files licence notice"),
        "files_this_repo_reads": _files_on(text),
        "read_or_measured": "read",
    }


def urban_portal(page: str) -> dict:
    """The Education Data Portal's own terms, not the federal data's.

    #13 exists because the underlying IPEDS and CCD data is US-government
    public domain and the wrapper's terms are a separate question. They are
    ODC-By v1.0 — permissive, and attribution-bearing, which is why the
    citation template is quoted rather than summarised.
    """
    text = flatten(page)
    return {
        "source": URBAN_PORTAL,
        "licence": _one(
            r"(All data made available via the Education Data Portal in any "
            r"form is licensed to you under the Open Data Commons Attribution "
            r"License \(ODC-By\) v1\.0)",
            text, URBAN_PORTAL, "the Open Data Commons licence sentence"),
        "citation": _one(
            r"(\[dataset names\], Education Data Portal.{0,200}?ODC Attribution "
            r"License)",
            text, URBAN_PORTAL, "the citation template it asks for"),
        "read_or_measured": "read",
    }
