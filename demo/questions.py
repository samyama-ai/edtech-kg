"""What the walkthrough asks, and in what order.

Split out of `demo/demo.py`, which had reached 567 lines against the 500-line review limit, and split by
SUBJECT: that module decides how a question is SHOWN — pacing, colour,
column widths, the pre-flight — and this one decides what is ASKED. They
change for different reasons. A new question is a content decision; a change
to how results are printed is not.

The order is the argument, so it lives here beside the questions rather than
in the runner. `tests/test_demo.py` holds it to that: tiers may not go
backwards, and every declared column must match what its query returns.
"""

from __future__ import annotations


# --------------------------------------------------------------------------
# The questions
# --------------------------------------------------------------------------
#
# One list, so the running order, the narration and the queries cannot drift
# apart — and so `--only` can pick from it by number.
#
#   tier      which of the five above
#   question  what a person would ask, in their words
#   aside     what to say while it runs
#   queries   (column headers, cypher) — several where one answer needs two

QUESTIONS: list[dict] = [
    # ---- tier 1: lookup ---------------------------------------------------
    dict(tier=1, question="Where did this come from?",
         aside="Every node carries the catalogue it was published in. "
               "Nothing here is typed in by hand.",
         queries=[(["source", "kind", "nodes"],
                   "MATCH (n) WHERE n.source IS NOT NULL "
                   "RETURN n.source, labels(n)[0] AS kind, count(n) AS nodes "
                   "ORDER BY nodes DESC")]),

    dict(tier=1, question="How big is this district's catalogue?",
         aside="The sitemap has 960 pages and most, but not all, are courses. "
               "The three kinds are the district's own, not ours — and four "
               "pages are pathways despite sitting at course depth, which is "
               "read off their markup rather than their address.",
         queries=[(["courses"], "MATCH (c:Course) RETURN count(c)"),
                  (["subjects"], "MATCH (s:Subject) RETURN count(s)"),
                  (["CTE pathways"], "MATCH (p:Pathway) RETURN count(p)")]),

    dict(tier=1, question="What does the district teach, by subject?",
         aside="A lookup. A spreadsheet does this perfectly — that is exactly "
               "why it is asked first.",
         queries=[(["subject", "courses"],
                   "MATCH (c:Course)-[:IN_SUBJECT]->(s:Subject) "
                   "RETURN s.name AS subject, count(c) AS courses "
                   "ORDER BY courses DESC LIMIT 10")]),

    dict(tier=1, question="What kinds of CTE pathway are published?",
         aside="Two categories, and they are the district's own, not ours.",
         queries=[(["kind", "pathways"],
                   "MATCH (p:Pathway) RETURN p.kind AS kind, count(p) AS pathways "
                   "ORDER BY pathways DESC")]),

    dict(tier=1, question="Which pathways publish no course list at all?",
         aside="A gap in the district's own publishing, visible the moment it "
               "is a graph. Nobody is looking for this today.",
         queries=[(["pathway with no courses listed"],
                   "MATCH (p:Pathway) WHERE NOT EXISTS { MATCH (p)-[:INCLUDES]->() } "
                   "RETURN p.name ORDER BY p.name")]),

    # ---- tier 2: one hop --------------------------------------------------
    dict(tier=2, question="Which courses make up the Information Technology pathway?",
         aside="One hop — a join. A spreadsheet is still fine here. Note the "
               "three named routes through it.",
         queries=[(["course", "route through the pathway", "credits"],
                   "MATCH (p:Pathway {name: 'Information Technology'})-[e:INCLUDES]->(c:Course) "
                   "RETURN c.name AS course, e.section AS route, e.credits AS credits "
                   "ORDER BY e.section, c.name")]),

    dict(tier=2, question="How many credits does each pathway take to complete?",
         aside="Published on the pages, never added up anywhere.",
         queries=[(["pathway", "courses", "credits"],
                   "MATCH (p:Pathway)-[e:INCLUDES]->(c:Course) "
                   "RETURN p.name AS pathway, count(c) AS courses, "
                   "sum(toFloat(e.credits)) AS credits "
                   "ORDER BY credits DESC LIMIT 10")]),

    dict(tier=2, question="How many courses state a prerequisite at all?",
         aside="Under a third. The catalogue publishes them as links between "
               "its own pages — not as prose. That is the whole reason they load.",
         queries=[(["courses in the catalogue"],
                   "MATCH (c:Course) RETURN count(c)"),
                  (["…stating a prerequisite"],
                   "MATCH (c:Course) WHERE EXISTS { MATCH (c)-[:REQUIRES]->() } "
                   "RETURN count(c)")]),

    dict(tier=2, question="What conditions are stated that are NOT another course?",
         aside="An audition, a recommendation, a programme enrolment. Held as "
               "data, never turned into a course link that the district did "
               "not publish.",
         queries=[(["condition", "courses"],
                   "MATCH (c:Course)-[:HAS_REQUIREMENT]->(r:Requirement) "
                   "RETURN substring(r.text, 0, 62) AS condition, count(c) AS courses "
                   "ORDER BY courses DESC LIMIT 8")]),

    # ---- tier 3: the shape of the catalogue -------------------------------
    dict(tier=3, question="Where can a student start — courses with nothing needed first?",
         aside="The courses that open a chain — the 'you can take this now' "
               "list, which no page in the catalogue carries.",
         queries=[(["courses that open a chain"],
                   "MATCH (c:Course) WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->() } "
                   "AND EXISTS { MATCH ()-[:REQUIRES]->(c) } RETURN count(c)")]),

    dict(tier=3, question="Which courses sit outside every chain and every pathway?",
         aside="Half of them. Not a criticism of the district: most courses "
               "genuinely stand alone. It is the honest denominator for "
               "everything that follows.",
         queries=[(["courses standing alone"],
                   "MATCH (c:Course) WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->() } "
                   "AND NOT EXISTS { MATCH ()-[:REQUIRES]->(c) } "
                   "AND NOT EXISTS { MATCH ()-[:INCLUDES]->(c) } RETURN count(c)")]),

    dict(tier=3, question="Which single course opens the most career pathways?",
         aside="One course, several different careers. This is the course a "
               "counsellor should push hardest, and nothing publishes it.",
         queries=[(["course", "pathways it appears in"],
                   "MATCH (c:Course)<-[:INCLUDES]-(p:Pathway) "
                   "RETURN c.name AS course, count(p) AS pathways "
                   "ORDER BY pathways DESC LIMIT 8")]),

    dict(tier=3, question="Which subjects gate the most of their own courses?",
         aside="Where the ladders are. Trade and Industrial Education is the "
               "most sequenced part of the catalogue.",
         queries=[(["subject", "courses with a prerequisite"],
                   "MATCH (c:Course)-[:IN_SUBJECT]->(s:Subject) "
                   "WHERE EXISTS { MATCH (c)-[:REQUIRES]->() } "
                   "RETURN s.name AS subject, count(c) AS gated "
                   "ORDER BY gated DESC LIMIT 8")]),

    # ---- tier 4: unknown depth --------------------------------------------
    dict(tier=4, question="What must a student pass to reach Studio Art 5?",
         aside="The depth is not known before you ask. This is where a "
               "relational database starts writing recursive CTEs.",
         queries=[(["steps back", "must pass first"],
                   "MATCH path = (:Course {name: 'Studio Art 5'})-[:REQUIRES*1..8]->(need:Course) "
                   "RETURN length(path) AS steps_back, need.name AS must_pass_first "
                   "ORDER BY length(path)")]),

    dict(tier=4, question="What is the longest chain anywhere in the catalogue?",
         aside="Four years, found without being told to look for four. Ask a "
               "spreadsheet this and you must guess the depth first.",
         queries=[(["from", "back to", "steps"],
                   "MATCH path = (a:Course)-[:REQUIRES*1..8]->(b:Course) "
                   "RETURN a.name AS start, b.name AS end, length(path) AS steps "
                   "ORDER BY length(path) DESC LIMIT 6")]),

    dict(tier=4, question="If a student does not pass Algebra 1, what closes off?",
         aside="The same traversal, inbound. This number is not published "
               "anywhere, by anyone. It only exists once the catalogue is a graph.",
         queries=[(["courses closed off"],
                   "MATCH (blocked:Course)-[:REQUIRES*1..8]->(:Course {name: 'Algebra 1'}) "
                   "RETURN count(DISTINCT blocked)")]),

    dict(tier=4, question="…and in which subjects?",
         aside="Chemistry, biology, IB and dual-enrolment science — not just "
               "more maths. That is the counselling point.",
         queries=[(["subject", "closed off"],
                   "MATCH (blocked:Course)-[:REQUIRES*1..8]->(:Course {name: 'Algebra 1'}) "
                   "MATCH (blocked)-[:IN_SUBJECT]->(s:Subject) "
                   "RETURN s.name AS subject, count(DISTINCT blocked) AS closed_off "
                   "ORDER BY closed_off DESC LIMIT 10")]),

    dict(tier=4, question="Which course closes off the most, across the whole catalogue?",
         aside="Every course ranked by what fails to open without it. One "
               "traversal over the entire graph — this is the intervention list.",
         queries=[(["course", "courses it closes off"],
                   "MATCH (blocked:Course)-[:REQUIRES*1..8]->(k:Course) "
                   "RETURN k.name AS course, count(DISTINCT blocked) AS closes_off "
                   "ORDER BY closes_off DESC LIMIT 10")]),

    dict(tier=4, question="Which courses gate the most Advanced Placement?",
         aside="AP is the visible prize. This is what stands between a student "
               "and it, several years earlier.",
         queries=[(["course", "AP courses behind it"],
                   "MATCH (ap:Course)-[:REQUIRES*1..8]->(k:Course) "
                   "WHERE ap.name CONTAINS 'AP ' "
                   "RETURN k.name AS course, count(DISTINCT ap) AS ap_behind_it "
                   "ORDER BY ap_behind_it DESC LIMIT 8")]),

    # ---- tier 5: two structures at once -----------------------------------
    dict(tier=5, question="What does a CTE pathway require that its own page never says?",
         aside="Two structures at once — the pathway's course list, and "
               "prerequisites of unknown depth reaching outside it. A family "
               "reads the IT applied-sciences page, sees twenty-one courses, "
               "and misses eleven more it never lists.",
         queries=[(["pathway", "requirement it never lists", "reached by"],
                   "MATCH (p:Pathway)-[:INCLUDES]->(c:Course)-[:REQUIRES*1..8]->(need:Course) "
                   "WHERE NOT EXISTS { MATCH (p)-[:INCLUDES]->(need) } "
                   "RETURN p.name AS pathway, need.name AS unlisted, "
                   "count(*) AS reached_by "
                   "ORDER BY reached_by DESC LIMIT 10")]),

    dict(tier=5, question="Which pathway is hardest to enter unprepared?",
         aside="Pathways ranked by how much unlisted groundwork they assume. "
               "The last question, and the one a district would pay for.",
         queries=[(["pathway", "unlisted prerequisites"],
                   "MATCH (p:Pathway)-[:INCLUDES]->(:Course)-[:REQUIRES*1..8]->(need:Course) "
                   "WHERE NOT EXISTS { MATCH (p)-[:INCLUDES]->(need) } "
                   "RETURN p.name AS pathway, count(DISTINCT need) AS unlisted "
                   "ORDER BY unlisted DESC LIMIT 8")]),

    # ---- the national spine, if it is loaded --------------------------
    #
    # edtech-kg#8 question 3. Skipped rather than shown empty when the spine
    # is absent — the published snapshot holds the district only.
    dict(tier=6, needs="Completion",
         question="Which Virginia colleges actually graduate registered nurses?",
         aside="IPEDS ships demographic TOTAL rows beside the breakdowns — "
               "race 99 and sex 99 — so the obvious sum(awards) counts the "
               "same award several times over. The wrong number runs FIRST, "
               "then two independent right ones: totals only, and breakdowns "
               "only. They agree, and that agreement is the check. "
               "A FOURTH figure answers the question the first three invite: "
               "these still add second majors to first majors, because "
               "`major_number` is a separate axis from race and sex, so the "
               "same student counts twice if they finished two. Restricting "
               "to first majors shows how much that is worth here — small, "
               "but named rather than left for the room to find. Every "
               "figure is read from the engine, the wrong one included.",
         queries=[(["the obvious query, counting each award more than once"],
                   'MATCH (c:Completion)-[:IN]->(p:Programme) '
                   'WHERE p.cip_code = "513801" RETURN sum(c.awards)'),
                  (["counted as totals"],
                   'MATCH (c:Completion)-[:IN]->(p:Programme) '
                   'WHERE p.cip_code = "513801" AND c.race = 99 AND c.sex = 99 '
                   'RETURN sum(c.awards)'),
                  (["counted as breakdowns"],
                   'MATCH (c:Completion)-[:IN]->(p:Programme) '
                   'WHERE p.cip_code = "513801" AND c.race <> 99 '
                   'AND c.sex <> 99 RETURN sum(c.awards)'),
                  (["counted as totals, first majors only"],
                   'MATCH (c:Completion)-[:IN]->(p:Programme) '
                   'WHERE p.cip_code = "513801" AND c.race = 99 '
                   'AND c.sex = 99 AND c.major_number = 1 '
                   'RETURN sum(c.awards)'),
                  (["college", "awards"],
                   'MATCH (c:Completion)-[:IN]->(p:Programme) '
                   'WHERE p.cip_code = "513801" AND c.race = 99 AND c.sex = 99 '
                   'MATCH (c)-[:AT]->(i:Institution) '
                   'WITH i, sum(c.awards) AS awards '
                   'RETURN i.name AS college, awards '
                   'ORDER BY awards DESC LIMIT 8'),
                  (["colleges with any nursing row"],
                   'MATCH (c:Completion)-[:IN]->(p:Programme) '
                   'WHERE p.cip_code = "513801" '
                   'MATCH (c)-[:AT]->(i:Institution) '
                   'WITH DISTINCT i RETURN count(i)')]),

]

TIERS = {
    1: "lookup — a spreadsheet does this perfectly",
    2: "one hop — a join. A spreadsheet is fine",
    3: "the shape of the catalogue — awkward, still possible",
    4: "unknown depth — recursive, and you must know the depth to write it",
    5: "two structures at once — unmaintainable as SQL",
    6: "a second source, in the same graph — Virginia's higher education",
}
