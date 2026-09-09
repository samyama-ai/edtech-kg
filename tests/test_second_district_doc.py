"""`docs/sources/second-district.md` held to the record that produced it.

The page answers edtech-kg#19 — does a second district's prerequisites resolve
the way PWCS's do — and the answer decides what kind of product this is. A
figure that drifts here changes a business conclusion, not a footnote.

**Whitespace is collapsed before matching.** The first version anchored on the
source's line wrap (`in the\\nfield`, `of\\n(\\d+)`), so reflowing prose that had
not changed failed the tests — which trains the next person to loosen the
guard rather than fix the page.

Nothing reaches the network.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "sources" / "second-district.md"
RECORD = json.loads((ROOT / "docs" / "sources"
                     / "second-district-measured.json").read_text("utf-8"))
RAW = DOC.read_text(encoding="utf-8")
#: One line, so a pattern spans a wrap without knowing where it falls.
PAGE = re.sub(r"\s+", " ", RAW)
DISTRICTS = RECORD["districts"]
PWCS = DISTRICTS["PWCS (Prince William County, VA)"]
APS = DISTRICTS["APS (Arlington, VA)"]


def test_every_district_has_a_row_and_every_row_is_measured():
    """The table is the finding. A district measured and left off it is a
    district whose absence changes the conclusion."""
    for name, found in DISTRICTS.items():
        assert name in PAGE, f"{name} was measured and is not on the page"
        if not found.get("candidate_course_paths"):
            continue
        row = re.search(
            rf"\| {re.escape(name)} \| (\d+) \| ([\d.]+)% \| "
            rf"\*\*([\d.]+)%\*\* \| (\d+)/(\d+)[^|]*\| (\d+) \|", PAGE)
        assert row, f"{name}'s row no longer parses"
        assert int(row.group(1)) == found["read"]
        assert float(row.group(2)) == found["percent_stating_in_either_field"]
        assert float(row.group(3)) == \
            found["percent_of_pages_with_a_typed_prerequisite"]
        assert [int(row.group(4)), int(row.group(5))] == [
            found["links_resolving_to_a_published_course"], found["links"]]
        assert int(row.group(6)) == found["candidate_course_paths"]


def test_the_headline_contrast_is_the_measured_one():
    """**The denominator is pages READ**, not "courses stating a
    prerequisite". The first version divided by the latter, counting any
    non-empty prose field as a statement — and that field carries "No lab
    class" and "This course is not eligible for high school credit". It
    inflated the denominator differently per district, so the comparison
    partly measured how chatty each district's notes are.
    """
    # **The sentence the finding now turns on**: Arlington states MORE
    # prerequisites and publishes fewer traversable ones.
    said = re.search(
        r"Arlington states more of them\s+than PWCS does — ([\d.]+)% of its "
        r"pages against\s+([\d.]+)%", PAGE)
    assert said, "the page no longer states the coverage contrast"
    assert float(said.group(1)) == APS["percent_stating_in_either_field"]
    assert float(said.group(2)) == PWCS["percent_stating_in_either_field"]
    assert APS["percent_stating_in_either_field"] > \
        PWCS["percent_stating_in_either_field"], (
        "Arlington no longer states more prerequisites than PWCS; the page's "
        "central sentence needs rewriting rather than re-running")

    traversable = re.search(
        r"([\d.]+)% of PWCS pages\s+carry a traversable prerequisite against\s+"
        r"([\d.]+)% of Arlington's", PAGE)
    assert traversable, "the page no longer states the traversable contrast"
    assert float(traversable.group(1)) == \
        PWCS["percent_of_pages_with_a_typed_prerequisite"]
    assert float(traversable.group(2)) == \
        APS["percent_of_pages_with_a_typed_prerequisite"]
    # A DIRECTION, not a ratio. Encoding `> 5x` was a tighter bar than the
    # finding needs — three observations at Arlington do not pin a multiple —
    # and a re-run at 5.2x would have left a stale "5.7 times" green.
    assert PWCS["percent_of_pages_with_a_typed_prerequisite"] > \
        APS["percent_of_pages_with_a_typed_prerequisite"]


def test_resolution_and_coverage_are_kept_apart():
    """The whole point of the rewrite. A district with one link that resolves
    scores 100% on resolution and nothing on coverage, and reporting only the
    first would say prerequisites generalise when they do not."""
    said = re.search(r"resolves —\s*(\d+)/(\d+) at PWCS", PAGE)
    assert said, "the page no longer reports PWCS's resolution rate"
    assert [int(said.group(1)), int(said.group(2))] == [
        PWCS["links_resolving_to_a_published_course"], PWCS["links"]]
    # EVERY district's, not only PWCS's — "resolution generalises" is a claim
    # about all of them and one figure cannot carry it.
    for name, found in DISTRICTS.items():
        if found["links"]:
            assert found["percent_of_links_that_resolve"] == 100.0, (
                f"{name} resolves {found['percent_of_links_that_resolve']}% "
                f"of its links; the page says resolution generalises")
    assert "Resolution, meanwhile, generalises completely" in PAGE


def test_the_page_states_the_89_percent_is_superseded():
    """The issue asks about 89% and the repo's own source page has since
    replaced it with 100%. Answering the question with a coverage figure
    without saying so compares two different metrics silently."""
    assert "89%" in PAGE and "superseded" in PAGE
    assert "course-prerequisites.md" in PAGE


def test_every_prose_example_on_the_page_comes_from_the_record():
    """**The test that had to change most.**

    Its first version asserted two literal strings — "No lab class" and "This
    course is not eligible for high school credit." — were present in the
    page, untied to the record. Neither is in the record and neither ever
    was: they were artifacts of an unbounded pattern reaching into a
    neighbouring field, and the bug was fixed while the paragraph quoting
    them stayed. So the only guard on the page's central claim was enforcing
    the retracted evidence, and correcting the prose would have failed it.

    Bound to the record now, in the direction that matters: a quote on the
    page must exist in `prose_examples`.
    """
    # Whitespace collapsed on BOTH sides. The record holds a literal
    # `&nbsp;` where the catalogue rendered one, and the page normalises it —
    # comparing the raw forms made a faithful quote look invented.
    recorded = {re.sub(r"\s+", " ", e["text"].replace("&nbsp;", " ")).strip()
                for found in DISTRICTS.values()
                for e in (found.get("prose_examples") or [])}
    assert recorded, "no prose examples recorded; the page's quotes rest on air"

    quoted = re.findall(r"\*“([^”]+)”\*", PAGE)
    assert quoted, "the page quotes no prose example"
    for said in quoted:
        assert said in recorded, (
            f"the page quotes {said!r}, which is in no district's "
            f"prose_examples. Either the record was re-measured and the page "
            f"was not, or the quote never came from a measurement.")


def test_the_page_records_that_the_notes_field_claim_was_retracted():
    """A page that silently dropped the claim would leave the next reader to
    rediscover why prose is counted as prerequisites — and the retracted
    version is the more intuitive one."""
    assert "an artifact of the bug" in PAGE
    assert "No lab class" in PAGE, (
        "the retracted quote must be named as retracted, or the correction "
        "is invisible")


def test_both_fields_are_counted_as_prerequisites():
    """The corrected reading. Excluding prose was based on evidence the fix
    invalidated, and it understated every district except PWCS."""
    for name, found in DISTRICTS.items():
        if not found.get("candidate_course_paths"):
            continue
        assert found["state_a_prerequisite_in_either_field"] == (
            found["with_a_typed_prerequisite"]
            + found["with_a_nonempty_prose_field"]), name


def test_the_sample_ceiling_is_described_as_a_ceiling():
    """Districts publishing fewer pages than the ceiling had their whole
    catalogue read. Calling it "60 pages each" was false for three of five."""
    assert f"Ceiling of {RECORD['sample_per_district']}" in PAGE
    # EVERY district's resolution figure, not only PWCS's.
    for name, found in DISTRICTS.items():
        if not found["links"]:
            continue
        assert re.search(
            rf"{found['links_resolving_to_a_published_course']}/{found['links']}",
            PAGE), f"{name}'s resolution figure is not on the page"
    # The sentence about reading whole catalogues is conditional — it applies
    # only while some district publishes fewer pages than the ceiling. Since
    # the pager is followed, none does; the sentence is a rule, not a claim
    # about today, so it stays and this asserts which case we are in.
    # A district reads fewer than the ceiling when a page did not answer or
    # turned out not to be a course. That is normal and the TABLE carries it —
    # the "courses read" column is the denominator, per district. What must
    # not happen is the page quoting the ceiling as though it were the
    # denominator.
    for name, found in DISTRICTS.items():
        if not found.get("candidate_course_paths"):
            continue
        assert found["read"] == (found["sampled"] - found["unreachable"]
                                 - found["sampled_but_not_a_course"]), name


def test_how_it_sampled_and_the_client_list_are_on_the_page():
    """The issue asks for a reproducible sample, and the districts must be
    traceable to the vendor's list rather than reading as hosts that happened
    to answer.

    **It asked for a seed, and a seed is not what makes this reproducible.**
    The population is a live catalogue: Arlington went 698 -> 697 paths
    between two runs and a seeded draw kept 4 of 60 pages. So the page states
    the METHOD, and the test requires the page and the record to name the
    same one — a page describing a draw the probe no longer makes is worse
    than one describing none.
    """
    assert "sha1" in RECORD["sampling"], (
        "the record no longer describes a hash-ordered sample; the page's "
        "claim and this test both need re-deriving from whatever replaced it")
    assert "sha1(path)" in PAGE, "the page does not say how it sampled"
    assert RECORD["vendor_client_list"] in PAGE


def test_the_enumeration_gap_is_a_measured_figure():
    """"An index crawl finds 73 of 817" lived only in a code comment, which
    is the one place this repo says a figure may not live. Both counts are in
    the record now and both are on the page."""
    # The CALIBRATION, which is what lets the other four population figures
    # be read as counts rather than floors. On PWCS both methods work, so the
    # crawl can be checked against a census.
    said = re.search(
        r"the crawl finds (\d+) of\s+the sitemap's (\d+)", PAGE)
    assert said, "the page no longer states the crawl's calibration"
    assert int(said.group(1)) == PWCS["courses_in_index_crawl"]
    assert int(said.group(2)) == PWCS["courses_in_sitemap"]
    assert PWCS["courses_in_index_crawl"] > PWCS["courses_in_sitemap"] * 0.9, (
        f"the crawl finds {PWCS['courses_in_index_crawl']} of "
        f"{PWCS['courses_in_sitemap']} — no longer close to a census, so the "
        f"other districts' population figures are floors and the page must "
        f"say so instead of calling them counts")

    without = [n for n, f in DISTRICTS.items() if not f.get("has_sitemap")]
    stated = re.search(r"(\d+) of the five publish no sitemap", PAGE)
    assert stated, "the page no longer counts the districts without a sitemap"
    assert int(stated.group(1)) == len(without)


def test_the_page_states_what_it_does_not_establish():
    """Five districts, one vendor, and Arlington's figure rests on a single
    typed prerequisite. The page has to say so, or it reads as a claim about
    US school districts."""
    assert "What this does not establish" in PAGE
    assert "one vendor" in PAGE
    # The sample is small and the page has to say so — three observations at
    # Arlington do not support a ratio quoted to one decimal.
    said = re.search(
        r"([\d.]+)% is\s+(\d+)/(\d+) and\s+([\d.]+)% is\s+(\d+)/(\d+)", PAGE)
    assert said, "the page no longer shows the counts behind its percentages"
    assert [int(said.group(2)), int(said.group(3))] == [
        PWCS["with_a_typed_prerequisite"], PWCS["read"]]
    assert [int(said.group(5)), int(said.group(6))] == [
        APS["with_a_typed_prerequisite"], APS["read"]]
    assert "should not be read to a\ndecimal" in DOC.read_text("utf-8") or \
        "should not be read to a decimal" in PAGE

    # "Resolves" is set membership, not a fetch. Saying so is the difference
    # between a measurement and an inference.
    assert "not a fetch" in PAGE and "HEAD-checked" in PAGE


def test_the_correction_is_recorded_not_quietly_replaced():
    """The first version reported Arlington at 1.7% and Clover Park with 51
    pages, because the crawl was not following the catalogue's pager — it read
    the first page of each index and sampled from that, a BIASED subset rather
    than a small one. A page that silently swapped the numbers would leave the
    next reader with no way to know the method changed."""
    # THREE, and the third is the largest — the metric redefinition that put
    # Arlington above PWCS. A page listing only the re-measurements would let
    # a reader mistake a redefinition for a re-run.
    assert "Three corrections are recorded" in PAGE
    assert "not following the catalogue's pager" in PAGE
    assert "not deduplicated" in PAGE
    assert "the metric was redefined" in PAGE

    # Each superseded figure NAMED, so the change is legible.
    for superseded in ("101 pages", "51", "10 resolving links",
                       "5.7 times as many", "60.0%", "39.0%"):
        assert superseded in PAGE, (
            f"the superseded figure {superseded!r} is not named; the "
            f"correction is invisible to a reader of the current page")
    assert str(APS["candidate_course_paths"]) in PAGE

    # And the sentinel correction, which is the one this repo had already
    # made once in course-prerequisites.md.
    assert "counted 'Prerequisite: None' as a stated" in PAGE
    assert "test_course_page_against_pwcs.py" in PAGE, (
        "the page must name the guard that now stops this recurring")


def test_every_district_entry_carries_the_same_keys():
    """The empty-district branch promises "the same keys as every other
    district". That was a comment until now — Kenosha was the only entry
    missing `sampled_but_not_a_course`, which is the exact KeyError the
    comment guards against."""
    populated = [f for f in DISTRICTS.values() if f.get("candidate_course_paths")]
    assert populated, "no populated district to compare against"
    expected = set(populated[0])
    for name, found in DISTRICTS.items():
        missing = expected - set(found)
        assert not missing, (
            f"{name} is missing {sorted(missing)}; a short entry is a "
            f"KeyError waiting for the first consumer that iterates the "
            f"record, and it reads as a missing measurement rather than a "
            f"measured zero")


def test_the_evidence_list_uses_the_form_the_guard_checks():
    """`test_every_prose_example_on_the_page_comes_from_the_record` matches
    the `*“…”*` form. A straight-quoted addition to the EVIDENCE list would
    bypass the guard on the page's central claim.

    Only that list. The page also quotes two RETRACTED strings — the "not
    eligible for high school credit" artifact and the superseded headline —
    and those are deliberately not in the record; a guard that demanded they
    be would forbid the page from naming what it withdrew.
    """
    evidence = PAGE[PAGE.index("One example from each district's record"):
                    PAGE.index("An earlier version of this page said")]
    straight = re.findall(r'\*"([^"]{20,})"\*', evidence)
    assert not straight, (
        f"the evidence list quotes {straight[:2]} with straight quotes, "
        f"which the prose-example guard does not see. Use the curly form.")
    assert re.findall(r"\*“[^”]{20,}”\*", evidence), (
        "the evidence list has no curly-quoted example; the guard above is "
        "checking nothing")
