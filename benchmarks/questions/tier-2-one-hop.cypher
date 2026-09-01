// Tier 2 — one hop. A node and its neighbours, or a count over them.
//
// edtech-kg#22. These PARSE against the engine; they are not asserted to
// return rows. Only the PWCS catalogue is loaded, so anything touching
// Programme, Occupation, Institution or Completion is a shape check against
// the declared schema.
//
// A `NEEDS:` line names properties the schema does not declare. It declares
// keys and, measured, almost nothing else (#123), so a traversal can parse,
// return null and look like an answer. Saying so is the point.

// Q21. This degree programme — what jobs does it lead to?
MATCH (p:Programme {cip_code: "11.0101"})-[:PREPARES_FOR]->(o:Occupation)
RETURN o.soc_code, o.name;

// Q22. I want this job. Which programmes lead to it?
MATCH (p:Programme)-[:PREPARES_FOR]->(o:Occupation {soc_code: "15-1252"})
RETURN p.cip_code, p.name;

// Q23. Which colleges near me offer this programme?
//   "Near me" is a Place join and Place is tier 2, blocked on #44 — so this
//   scopes by the Place a caller already holds rather than by distance.
MATCH (i:Institution)-[:OFFERS]->(:Programme {cip_code: "11.0101"})
MATCH (i)-[:LOCATED_IN]->(pl:Place {id: "state|VA"})
RETURN i.unitid, i.name;

// Q24. Of those, which actually graduate people in it, rather than listing it?
//   The DISTINCTION this question exists for: OFFERS is a listing, Completion
//   is an award conferred. An institution can do the first and not the second.
MATCH (i:Institution)-[:OFFERS]->(p:Programme {cip_code: "11.0101"})
MATCH (cm:Completion)-[:AT]->(i)
MATCH (cm)-[:IN]->(p)
RETURN i.unitid, i.name, sum(cm.awards) AS conferred
ORDER BY conferred DESC;

// Q25. Which institutions award this programme at certificate level?
MATCH (cm:Completion {award_level: "Certificate"})-[:IN]->(:Programme {cip_code: "11.0101"})
MATCH (cm)-[:AT]->(i:Institution)
RETURN DISTINCT i.unitid, i.name;

// Q26. Which courses in this district list a prerequisite at all?
// 229 of 791. The REQUIRES edge, not the free-text Requirement node — Q16
// counts the other kind, and conflating them is what #74 was about.
MATCH (c:Course {district: "Prince William County Public Schools"})-[:REQUIRES]->(:Course)
RETURN count(DISTINCT c) AS courses_with_a_prerequisite;

// Q27. What is the immediate prerequisite of this course?
// IMMEDIATE — one hop, not the closure. Q69 asks for the ancestor set.
MATCH (:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-2"})-[:REQUIRES]->(p:Course)
RETURN p.url, p.name;

// Q28. Which courses name this one as their prerequisite?
// The same edge read backwards, which is the half a relational schema makes
// you write a second query for.
MATCH (c:Course)-[:REQUIRES]->(:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-1"})
RETURN c.url, c.name;

// Q29. How many people graduated in this programme nationally last year?
//   AWARDS, not rows. A Completion is a demographic cell — 9,026,310 rows
//   describe 10,620,172 awards (#43) — so counting nodes answers a different
//   question from the one asked.
MATCH (cm:Completion)-[:IN]->(:Programme {cip_code: "11.0101"})
RETURN sum(cm.awards) AS graduates;

// Q30. Which districts contain this school?
MATCH (s:School {ncessch: "510126000341"})-[:IN_DISTRICT]->(d:District)
RETURN s.name, d.leaid, d.name;

// Q31. Which programmes does this institution offer that map to healthcare occupations?
//   Healthcare is SOC major group 29. Matched on the code's own prefix rather
//   than on an occupation name, because the code is the thing the crosswalk
//   publishes and a name is not declared anywhere (#123).
MATCH (:Institution {unitid: "100654"})-[:OFFERS]->(p:Programme)
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code STARTS WITH "29-"
RETURN DISTINCT p.cip_code, p.name;

// Q32. Which occupations does this programme lead to that need only a certificate?
//   [caveat: award level is measured, entry requirement is not]
//   What is answerable is what this programme is AWARDED at, not what the
//   occupation REQUIRES. Nothing published here says an occupation's entry
//   requirement, so the caveat is the answer's, not the query's.
MATCH (p:Programme {cip_code: "11.0101"})-[:PREPARES_FOR]->(o:Occupation)
MATCH (cm:Completion)-[:IN]->(p)
WHERE cm.award_level = "Certificate"
RETURN DISTINCT o.soc_code, o.name;

// Q33. What do graduates of this programme earn?
//   [caveat: federal-aid recipients only; that cohort is not everyone]
//   NEEDS: EarningsRecord.median, EarningsRecord.year, EarningsRecord.source
MATCH (er:EarningsRecord)-[:FOR_PROGRAMME]->(:Programme {cip_code: "11.0101"})
RETURN er.year, er.median, er.source ORDER BY er.year DESC;

// Q34. Which courses at this school have no prerequisite — the entry points?
//   ABSENCE, written as NOT EXISTS { MATCH } — a pattern inside WHERE does not
//   parse on the engine this repo pins. See docs/schema.md.
MATCH (:School {ncessch: "510126000341"})-[:TEACHES]->(c:Course)
WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->(:Course) }
RETURN c.url, c.name;

// Q35. Which occupations are reachable from programmes this institution offers?
MATCH (:Institution {unitid: "100654"})-[:OFFERS]->(:Programme)-[:PREPARES_FOR]->(o:Occupation)
RETURN DISTINCT o.soc_code, o.name;

// Q36. Which programmes here are dead ends, mapping to only one occupation?
//   ONE, not zero. A programme mapping to nothing is a different finding —
//   it is absent from the crosswalk rather than narrow within it.
MATCH (p:Programme)-[:PREPARES_FOR]->(o:Occupation)
WITH p, count(DISTINCT o) AS reaches
WHERE reaches = 1
RETURN p.cip_code, p.name;

// Q37. Which occupations can be reached from the most different programmes?
MATCH (p:Programme)-[:PREPARES_FOR]->(o:Occupation)
WITH o, count(DISTINCT p) AS routes
RETURN o.soc_code, o.name, routes ORDER BY routes DESC LIMIT 20;

// Q42. How many pathways does the Credential Registry publish?
//   [caveat: 98 measured at the source, and the Registry's data may not be
//   loaded — its terms grant internal use only (#56). So this counts what is
//   IN the graph, which is the district's pathways, and the Registry's 98 are
//   a source figure rather than a graph figure.]
MATCH (pw:Pathway) RETURN pw.district, count(pw) AS pathways;

// Q38, Q39, Q40 and Q41 are marked ❌ and have no query. Student records are
// out of scope by choice; no public source links a course to a programme's
// entry requirement, names an employer, or maps a course to a competency.
// Writing the nearest traversal for any of them would answer a different
// question while looking like an answer to the one asked — which is the
// failure #22 exists to catch.
