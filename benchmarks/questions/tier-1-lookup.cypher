// Tier 1 — lookup. One node, or one node and its immediate properties.
//
// edtech-kg#22: every question marked answerable in docs/questions.md gets the
// traversal that answers it. A question that cannot be written is not
// answerable and its mark is wrong — which is the cheapest test the ontology
// gets, and it runs before any data is loaded.
//
// These PARSE against the engine. They are not asserted to return rows: only
// the PWCS catalogue is loaded, so anything touching Programme, Occupation,
// Institution, School or Completion is a shape check against the schema.
//
// Written for the engine this repo pins. A pattern inside WHERE does not
// parse — see the table in docs/schema.md — so absence is expressed as
// `NOT EXISTS { MATCH ... }` throughout.

// Q1. What is this programme called, and what is its CIP code?
MATCH (p:Programme {cip_code: "11.0101"}) RETURN p.cip_code, p.name;

// Q2. What occupation does this SOC code name?
MATCH (o:Occupation {soc_code: "15-1252"}) RETURN o.soc_code, o.name;

// Q3. How many institutions are in the directory?
MATCH (i:Institution) RETURN count(i) AS institutions;

// Q4. How many schools and districts are there?
MATCH (s:School) RETURN count(s) AS schools;
MATCH (d:District) RETURN count(d) AS districts;

// Q5. How many CIP-SOC mappings exist?
// The EDGE, not the endpoints — a programme preparing for four occupations is
// four mappings, which is what the crosswalk publishes.
MATCH (:Programme)-[m:PREPARES_FOR]->(:Occupation) RETURN count(m) AS mappings;

// Q6. How many distinct programmes appear in the crosswalk?
// Programmes that MAP, not every declared programme. 2,143 exist and 1,949
// reach an occupation; this asks the second number.
MATCH (p:Programme)-[:PREPARES_FOR]->(:Occupation) RETURN count(DISTINCT p) AS programmes;

// Q7. How many distinct occupations?
MATCH (:Programme)-[:PREPARES_FOR]->(o:Occupation) RETURN count(DISTINCT o) AS occupations;

// Q8. How many courses does this district publish?
MATCH (c:Course {district: "Prince William County Public Schools"})
RETURN count(c) AS courses;

// Q9. What are this course's grade levels and length?
//   [caveat: grade levels yes, LENGTH no — no source publishes it]
//   The catalogue carries `field-grades` and `field-credits` and no length or
//   duration field at all. Credits are not length: a one-credit course can run
//   a semester or a year. So this answers the half that exists and does not
//   dress the other half in a property nothing writes (#123).
MATCH (c:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-2"})
RETURN c.name, c.grade_levels;

// Q10. Which schools teach this course?
MATCH (s:School)-[:TEACHES]->(c:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-2"})
RETURN s.ncessch, s.name;

// Q11. What award levels does this institution grant?
MATCH (cm:Completion)-[:AT]->(i:Institution {unitid: "100654"})
RETURN DISTINCT cm.award_level;

// Q12. Where is this institution, and is it public or private?
//
//   `pl.state` is NOT used, and that is a different objection. `Place` is
//   keyed `"<kind>|<published identifier>"` — "state|VA" — so a state IS a
//   Place, and `state` as a property contradicts the key's own shape rather
//   than merely being undeclared. The id is what the model commits to.
MATCH (i:Institution {unitid: "100654"})-[:LOCATED_IN]->(pl:Place)
RETURN i.name, i.control, pl.id;

// Q13. How many people completed this programme at this institution?
MATCH (cm:Completion)-[:AT]->(i:Institution {unitid: "100654"})
MATCH (cm)-[:IN]->(p:Programme {cip_code: "11.0101"})
RETURN sum(cm.awards) AS completions;

// Q14. What is this course's description, as the district publishes it?
MATCH (c:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-2"})
RETURN c.name, c.description, c.source;

// Q15. Which courses are flagged as career-and-technical education?
// Via the PATHWAY, not a flag on the course. The catalogue publishes CTE as a
// pathway that includes courses; no course carries a CTE property, which is
// why this reads as a traversal rather than a lookup.
MATCH (pw:Pathway {kind: "career pathway"})-[:INCLUDES]->(c:Course)
RETURN DISTINCT c.url, c.name;

// Q16. How many courses carry a free-text requirement rather than a linked one?
// Requirement is a NODE precisely so this is countable. A course with both is
// counted once here — it states a condition that is not a course reference.
MATCH (c:Course)-[:HAS_REQUIREMENT]->(:Requirement)
RETURN count(DISTINCT c) AS courses_with_free_text;

// Q17. What does this occupation pay?  [caveat: source named, not yet measured]
// EarningsRecord is declared and empty. The traversal is right; the answer is
// not available until a BLS loader exists.
//   NEEDS: EarningsRecord.median, EarningsRecord.source, EarningsRecord.year
MATCH (er:EarningsRecord)-[:FOR_OCCUPATION]->(o:Occupation {soc_code: "15-1252"})
RETURN er.year, er.median, er.source;

// Q18. Is this occupation growing or shrinking?  [caveat: not yet measured]
// Two records for one occupation, compared. Nothing loaded supplies them.
//   NEEDS: EarningsRecord.employment, EarningsRecord.year
MATCH (er:EarningsRecord)-[:FOR_OCCUPATION]->(o:Occupation {soc_code: "15-1252"})
RETURN o.soc_code, er.year, er.employment ORDER BY er.year;

// Q19 is NOT here. It asked what a programme costs, and nothing in this
// schema holds a cost — no node, no property. Writing the nearest traversal
// (earnings for the programme) would have answered a different question while
// looking like an answer to this one, which is the failure #22 exists to
// catch. It is re-marked in docs/questions.md, with the reason.
