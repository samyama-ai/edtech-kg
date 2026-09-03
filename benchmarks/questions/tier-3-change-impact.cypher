
// Tier 3 — change impact. "This changed; what is affected?"
//
// edtech-kg#22. The tier the regulatory KG shares its shape with: a rule
// moves, and the question is which things downstream move with it. Answering
// it is a traversal from the changed node outward, which is the operation a
// relational schema makes you write once per depth.
//
// These PARSE; they are not asserted to return rows. A `NEEDS:` line names
// properties the schema does not declare (#123).
//
// Each is written as "the change has happened, now find what it touched" —
// so they are read against the graph as it stands, not against a diff. What
// a change actually BREAKS is the second half, and where the graph cannot
// answer it the query says which half it answers.
// Q43. The CIP-SOC crosswalk is revised. Which programmes change what they lead to?
//   SUBSTITUTES: what a programme reaches NOW, not what changes.
//     Comparing two crosswalk revisions needs both loaded and only one is,
//     so the comparison is a diff of two runs rather than a traversal.
//   NEEDS: Programme.name
//   The direct blast radius: what a programme currently reaches. Comparing
//   two revisions needs both loaded, and only one is — so this is the "before"
//   half, and the comparison is a diff of two runs rather than a traversal.
MATCH (p:Programme)-[:PREPARES_FOR]->(o:Occupation)
RETURN p.cip_code, p.name, collect(o.soc_code) AS leads_to
ORDER BY p.cip_code;

// Q45. An occupation's outlook is downgraded. Which programmes feed it?
//   NEEDS: Programme.name
MATCH (p:Programme)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code = "15-1252"
RETURN p.cip_code, p.name;

// Q46. A programme is discontinued at an institution. What was it feeding?
//   NEEDS: Occupation.name
//   Scoped to the institution: the programme continues elsewhere, and the
//   loss is local. Answering nationally would overstate it.
MATCH (i:Institution)-[:OFFERS]->(p:Programme)
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
WHERE i.unitid = "100654" AND p.cip_code = "11.0101"
RETURN o.soc_code, o.name;

// Q47. This occupation now requires a licence. Which programmes lead to it?
//   NEEDS: Programme.name
//   The same traversal as Q45 and deliberately not merged with it: the
//   question differs in what the answer is FOR, and a benchmark that collapses
//   two questions into one query cannot show that both were asked.
MATCH (p:Programme)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code = "29-1141"
RETURN p.cip_code, p.name;

// Q48. A course is removed from the district catalogue. Which courses lose a prerequisite?
// IMMEDIATE dependants, not the closure. A course losing its only prerequisite
// becomes an entry point; one losing a prerequisite it has two of does not.
// Both are reported, because the difference is the finding.
MATCH (dependant:Course)-[:REQUIRES]->(gone:Course)
WHERE gone.url = "https://catalog.pwcs.edu/agriculture-food-and-natural-resources/landscaping-1"
OPTIONAL MATCH (dependant)-[:REQUIRES]->(other:Course)
WITH dependant, count(other) AS prerequisites
RETURN dependant.url, dependant.name, prerequisites - 1 AS left_after_removal;

// Q49. A course's prerequisite changes. Which downstream courses are affected?
// THE CLOSURE, unbounded. This is the blast-radius question and the reason
// depth is unknown: a chain runs as deep as the catalogue does, and the
// answer is every course reachable by following REQUIRES backwards.
MATCH (downstream:Course)-[:REQUIRES*]->(c:Course)
WHERE c.url = "https://catalog.pwcs.edu/agriculture-food-and-natural-resources/landscaping-1"
RETURN DISTINCT downstream.url, downstream.name;

// Q50. A CIP code is retired between revisions. What breaks?
//   NEEDS: Completion.awards
//   Three things hang off a programme and they break differently: the
//   occupations it reached, the institutions that offered it, and the awards
//   already conferred under it. The last does not "break" — those graduates
//   still graduated — which is why it is counted rather than listed as lost.
MATCH (p:Programme)
WHERE p.cip_code = "11.0101"
OPTIONAL MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
OPTIONAL MATCH (i:Institution)-[:OFFERS]->(p)
OPTIONAL MATCH (cm:Completion)-[:IN]->(p)
RETURN count(DISTINCT o) AS occupations_unreached,
       count(DISTINCT i) AS institutions_affected,
       sum(cm.awards) AS awards_already_conferred;

// Q51. A SOC code is split into two. Which programmes now point at both?
//   NEEDS: Programme.name
MATCH (p:Programme)-[:PREPARES_FOR]->(a:Occupation)
MATCH (p)-[:PREPARES_FOR]->(b:Occupation)
WHERE a.soc_code = "15-1252" AND b.soc_code = "15-1253"
RETURN p.cip_code, p.name;

// Q52. An institution closes. Which occupations lose a route in this region?
//   NEEDS: Occupation.name
//   LOSE A ROUTE, not "are reached by it". An occupation another institution
//   in the same Place also reaches has not lost anything, and reporting it
//   would overstate the closure — which is the mistake this question is
//   really testing for.
// ONE connected path in the subquery. Two `MATCH` clauses inside
// `NOT EXISTS { }` do not parse on this engine — measured, not assumed — so
// the alternative route is written as a single walk from the occupation back
// out to another institution in the same Place.
MATCH (closing:Institution)-[:LOCATED_IN]->(pl:Place)
MATCH (closing)-[:OFFERS]->(:Programme)-[:PREPARES_FOR]->(o:Occupation)
WHERE closing.unitid = "100654"
  AND NOT EXISTS {
  MATCH (o)<-[:PREPARES_FOR]-(:Programme)<-[:OFFERS]-(other:Institution)-[:LOCATED_IN]->(pl)
  WHERE other.unitid <> closing.unitid
}
RETURN DISTINCT o.soc_code, o.name;

// Q53. A school stops offering a course. Which pathways at that school break?
// A pathway breaks when a course it includes is no longer taught there. The
// pathway is a district publication and the offering is a school fact, so the
// break is the join of the two rather than a property of either.
MATCH (s:School)-[:TEACHES]->(c:Course)
MATCH (pw:Pathway)-[:INCLUDES]->(c)
WHERE s.ncessch = "510126000341" AND c.url = "https://catalog.pwcs.edu/agriculture-food-and-natural-resources/landscaping-1"
RETURN pw.url, pw.name;

// Q54. A district adds a course. What does it newly make reachable?
// Everything downstream of it, which is the mirror of Q49 — the same closure
// walked in the same direction, asked as a gain rather than a loss.
MATCH (unlocked:Course)-[:REQUIRES*]->(c:Course)
WHERE c.url = "https://catalog.pwcs.edu/agriculture-food-and-natural-resources/landscaping-1"
RETURN count(DISTINCT unlocked) AS newly_reachable;

// Q55. Earnings data is revised. Which programme rankings move?
//   [caveat: unmeasured source — no earnings loader exists]
//   NEEDS: EarningsRecord.median, EarningsRecord.year, Programme.name
//   The RANKING, which is what moves. A revision that lifts every figure
//   equally changes no ranking, so the answer is an order rather than a set.
MATCH (er:EarningsRecord)-[:FOR_PROGRAMME]->(p:Programme)
RETURN p.cip_code, p.name, er.year, er.median
ORDER BY er.median DESC;

// Q56. A course is renamed. Do its inbound prerequisite links survive?
// YES, and this shows why: the edge is between nodes keyed on `url`, and a
// rename changes `name`. The query returns the dependants of a course by URL
// and reports the name alongside, so a rename is visible in the output and
// absent from the join.
MATCH (dependant:Course)-[:REQUIRES]->(renamed:Course)
WHERE renamed.url = "https://catalog.pwcs.edu/agriculture-food-and-natural-resources/landscaping-1"
RETURN renamed.url, renamed.name, count(dependant) AS inbound_links;

// Q60. The crosswalk gains a mapping. Which occupations become newly reachable
//   SUBSTITUTES: what is reachable NOW, not what is newly reachable.
//     "Newly" is a comparison against a previous revision; one is loaded.
// from this institution?
//   NEEDS: Occupation.name
//   Reachable NOW. "Newly" is a comparison against a previous revision, and
//   only one is loaded — so this answers the after half, and the newness is a
//   set difference between two runs.
MATCH (i:Institution)-[:OFFERS]->(:Programme)-[:PREPARES_FOR]->(o:Occupation)
WHERE i.unitid = "100654"
RETURN DISTINCT o.soc_code, o.name;

// Q44, Q57, Q58 and Q59 are marked ❌ and have no query. Student records are
// out of scope by choice; nobody publishes state graduation requirements,
// accreditation status or a course-to-competency map as data this graph can
// read. Q57 in particular is #41 and unresearched rather than impossible.
