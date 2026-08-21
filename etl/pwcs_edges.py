"""Building the edges — pure, so the arithmetic can be checked without an engine.

Split out of `etl/load_pwcs.py` when it passed the 500-line review limit. Split
by SUBJECT rather than by length: these two functions decide WHICH edges exist
and how many rows collapse into each, and they touch nothing but dictionaries.
`load_pwcs` is the writing — which statements, in what order, and the read-back
that checks they landed.

Both resolve against the COURSE index rather than every published page, and
both report a row naming a published non-course page separately from a row
naming nothing. Those are two different facts about the catalogue, and the edge
that conflated them wrote no edge while still counting one.
"""

from __future__ import annotations

from etl import probe_pwcs as source


# --------------------------------------------------------------------------
# Building the edges — pure, so the arithmetic can be tested without an engine
# --------------------------------------------------------------------------

def prerequisite_pairs(courses: list[dict], by_path: dict,
                       course_by_path: dict) -> dict:
    """Course -> course, resolved and deduped.

    **Resolved against the COURSE index, not every published page.** This is
    the guard `pwcs_source.read` already applies to pathway rows, and it was
    missing on the edge this graph exists for. `by_path` holds subject and
    pathway pages too, so a prerequisite link pointing at one of those
    resolved as if it were a course — and the statement written for it is
    `MATCH (a:Course {…}), (b:Course {…})` where `b` is a `:Subject`. The MATCH
    finds nothing, no edge is written, and the counter still increments.
    `verify()` then reports a mismatch with nothing on the page to say why:
    the count and the graph disagreeing silently, which is the exact failure
    this module argues against everywhere else.

    Three outcomes, counted separately because they are three different facts:
    resolved, points at a page that did not parse (`unresolved`), and points
    at a published page that is not a course (`off_level`). Both are zero
    against this catalogue today — a property of this publisher, measured, not
    assumed.

    **Deduped for the same reason INCLUDES is.** An edge MERGE matches on
    start, type and end alone (#77), so two links on one page naming the same
    course produce two MERGEs, ONE edge and a counter of two — and `verify()`
    then exits non-zero on a catalogue that is perfectly well-formed. It does
    not happen at 240 of 240 today; the shape should not differ between the two
    edges on the strength of that.
    """
    pairs, unresolved, off_level = [], 0, []
    for record in courses:
        for link in record["prerequisite_links"]:
            path = source.path_of(link["href"])
            if path in course_by_path:
                pairs.append((record["url"], course_by_path[path]))
            elif path in by_path:
                # Published, parsed, and not a course. Named rather than
                # counted: one of these is a catalogue fact worth reading.
                off_level.append(by_path[path])
            else:
                # Measured at zero today, never ASSUMED to be zero.
                unresolved += 1
    return {"pairs": list(dict.fromkeys(pairs)),
            "duplicated": len(pairs) - len(set(pairs)),
            "unresolved": unresolved,
            "off_level": off_level}


def pathway_edges(pathways: list[dict], by_path: dict,
                  course_by_path: dict) -> dict:
    """Pathway -> course, one edge per pair, with the sections folded in.

    **Resolved against the COURSE index, like REQUIRES.** This resolved through
    `by_path`, which holds subject and pathway pages too, and then wrote
    `MATCH (c:Course {url: …})` — so a row naming a subject page resolved, the
    MATCH found nothing, no edge was written, and the counter still
    incremented. The same off-level defect `prerequisite_pairs` was fixed for,
    on the other edge. `pwcs_source.read` already guards it at parse time by
    resolving rows against the course paths; this closes it at write time too,
    so the two layers agree rather than one covering for the other.

    Rows that resolve to a published page which is not a course are counted
    separately from rows that resolve to nothing — two different facts.

    **Resolved through the index, not through `absolute(href)`.** That matched
    on a re-normalised href while Course NODES are created from the sitemap URL
    verbatim, and the two normalise differently.

    A course in two named sections of one pathway is a real fact and cannot be
    two edges, so the section names are joined and `sections` counts how many
    were folded in. The credit value is kept from the first row and any
    disagreement is counted — the section names were carefully preserved and
    the credits were not, which is the same silent loss #77 is about.
    """
    grouped: dict[tuple[str, str], dict] = {}
    unlinkable, off_level, resolved = 0, [], 0
    for record in pathways:
        for course in record["courses"]:
            path = source.path_of(course["url"])
            if path not in course_by_path:
                if path in by_path:
                    off_level.append(by_path[path])
                else:
                    unlinkable += 1
                continue
            resolved += 1
            entry = grouped.setdefault((record["url"], course_by_path[path]),
                                       {"sections": [], "rows": 0,
                                        "credits": course["credits"],
                                        "credit_values": set()})
            # Rows folded into THIS edge. `len(sections)` counts distinct
            # names, which is not the same number the moment two rows share a
            # section or one carries none.
            entry["rows"] += 1
            if course["section"] and course["section"] not in entry["sections"]:
                entry["sections"].append(course["section"])
            entry["credit_values"].add(course["credits"])
    return {"grouped": grouped, "unlinkable": unlinkable,
            "off_level": off_level,
            # ROWS that folded into an edge, not extra section NAMES.
            #
            # This was `sum(len(sections) - 1 …)`, and `sections` holds
            # DISTINCT NON-EMPTY names — so two rows for one pair in the same
            # section counted 0, a row with an empty section counted 0, and
            # three rows across two sections counted 1 rather than 2. The
            # console line says "N published rows are a course in a second
            # section", `e.sections` goes onto the edge as "how many were
            # folded in", and `verify()` cannot see the difference because
            # `includes` is `len(grouped)` either way. Rows could vanish
            # beyond what was reported — the #77 failure this whole section
            # exists to prevent, one level up.
            #
            # `resolved - len(grouped)` is independent of section names and
            # cannot drift. It agrees at 17 on this catalogue only because
            # every duplicate happens to fall in a distinct named section,
            # which is a property of the data and not of the code.
            "collapsed": resolved - len(grouped),
            "resolved_rows": resolved,
            "conflicting": sum(1 for e in grouped.values()
                               if len(e["credit_values"]) > 1)}
