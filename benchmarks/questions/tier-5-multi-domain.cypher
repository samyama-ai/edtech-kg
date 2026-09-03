// Tier 5 — multi-domain. A question crossing from one source into another.
//
// edtech-kg#22, and the tier where the exercise found the most. TEN of the
// fourteen cannot be answered. FOUR of those ten trace to one cause:
// **there is no academic edge from a district Course to a Programme or an
// Occupation.** SIX across the document, counted in `docs/questions.md`.
// The only route in the schema runs through
// Place, which says "a college in the same state offers this" and not "this
// course prepares you for it".
//
// That is #66, the rules joining secondary to post-secondary, and this tier is
// what it costs. Tier 5 is where the graph's two halves were supposed to meet;
// measured, they touch only through geography.
//
// Four are written, all on the post-secondary side where the edges exist.

// Q82. Are high-earning occupations reachable from programmes offered in low-income districts?
//   [caveat: the equity framing needs an income measure this graph does not hold]
//   NEEDS: EarningsRecord.median, EarningsRecord.year, Occupation.name
//   The POST-SECONDARY half only. "Low-income district" is a school-side fact
//   and joins to a Place, not to a programme, so this answers what a Place's
//   institutions reach and at what earnings — leaving the income measure to a
//   caller who has one.
//   TWO THINGS THE JOIN HAS TO SAY. `99-9999` is the crosswalk's NO MATCH
//   sentinel and not an occupation; it would sit in this ranking as one. And
//   EarningsRecord is one row per subject x cohort x year x source, so a bare
//   join fans out and `ORDER BY er.median` ranks a mixture of cohorts against
//   each other — pinned here to the latest year each occupation has. Source
//   and cohort stay unpinned because the schema does not carry them yet
//   (#21, #37).
MATCH (place:Place)<-[:LOCATED_IN]-(:Institution)-[:OFFERS]->(p:Programme)
WHERE place.id = "state|VA"
WITH p
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code <> "99-9999"
WITH o
MATCH (er:EarningsRecord)-[:FOR_OCCUPATION]->(o)
WITH o, max(er.year) AS latest
//   A bound variable does NOT go in an inline property map here — measured:
//   `{year: latest}` is a parse error, not a match on the bound value.
MATCH (r:EarningsRecord)-[:FOR_OCCUPATION]->(o)
WHERE r.year = latest
RETURN DISTINCT o.soc_code, o.name, latest, r.median
ORDER BY r.median DESC LIMIT 25;

// Q85. Which occupations pay above median but need only a certificate?
//   [caveat: award level is what a programme confers, not what an occupation requires]
//   NEEDS: Completion.award_level, EarningsRecord.median, Occupation.name
//   ABOVE MEDIAN, computed. It said "above median" and returned every
//   reachable occupation at any wage — the question's own condition dropped.
//   There is no percentile function and no GDS here, so the midpoint is the
//   middle of the sorted list of every occupation's median; measured, `size()`
//   over a list and indexing it by an expression both work.
//   The distinction Q32 also turns on, and it is the whole caveat: this finds
//   occupations reachable from programmes AWARDED at certificate level. What
//   an occupation REQUIRES is not published anywhere this graph reads.
MATCH (any:EarningsRecord)-[:FOR_OCCUPATION]->(:Occupation)
WITH any.median AS m ORDER BY m
WITH collect(m) AS medians
WITH medians[size(medians) / 2] AS midpoint
MATCH (cm:Completion)-[:IN]->(p:Programme)
WHERE cm.award_level = "Certificate"
WITH midpoint, p
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code <> "99-9999"
WITH midpoint, o
MATCH (er:EarningsRecord)-[:FOR_OCCUPATION]->(o)
WHERE er.median > midpoint
RETURN DISTINCT o.soc_code, o.name, er.median, midpoint
ORDER BY er.median DESC LIMIT 25;

// Q86. Is this programme oversupplied — more graduates than the occupation absorbs?
//   [caveat: completions are measured, absorption is not]
//   NEEDS: Completion.awards, Occupation.name
//   Half a question, and the half that exists is the supply. Nothing published
//   here says how many an occupation absorbs, so the ratio the question wants
//   cannot be computed — only its numerator.
MATCH (cm:Completion)-[:IN]->(p:Programme)
WHERE p.cip_code = "11.0101"
WITH cm, p
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code <> "99-9999"
RETURN o.soc_code, o.name, sum(cm.awards) AS graduates_supplied
ORDER BY graduates_supplied DESC;

// Q91. Which institution offers the most efficient route to this occupation?
//   [caveat: efficiency here is award level, not time or cost — neither is held]
//   NEEDS: Completion.award_level, Institution.name
//   EFFICIENT is doing a lot of work in the question. What is measurable is
//   the award level a programme reaching the occupation is conferred at; a
//   certificate is a shorter route than a bachelor's, and that ordering is the
//   answer this graph can give.
MATCH (i:Institution)-[:OFFERS]->(p:Programme)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code = "29-1141"
WITH i, p
MATCH (cm:Completion)-[:AT]->(i)
MATCH (cm)-[:IN]->(p)
RETURN DISTINCT i.unitid, i.name, cm.award_level;

// Ten have no query. Four are one cause.
//
// Q81, Q83, Q89 and Q90 ask a district question about occupations — the four.
// Q75 and Q62 ask the same thing from the other side in tier 4, which makes
// SIX across the document. Five of the six are blocked; Q62 is ⚠️ rather than
// ❌ because its narrowed reading, course to course, is fully answered. They
// all need a Course to reach a Programme or an Occupation academically, and
// it cannot: the walk
// goes Course <-TEACHES- School -IN_DISTRICT-> District -LOCATED_IN-> Place
// <-LOCATED_IN- Institution -OFFERS-> Programme, which is geography wearing an
// academic answer's clothes. Re-marked ❌, and #66 is the issue.
//
// Q84 asks the gap between who ENROLS and who completes. Nothing in the schema
// or in any loader holds an enrolment count — `Completion` is awards conferred
// — so the gap has one side. Re-marked ❌.
//
// Q92 asks the cheapest programme reaching each occupation. Cost is not in the
// schema, which is Q19's finding one tier up. Re-marked ❌.
//
// Q87, Q88, Q93 and Q94 were already ❌: no public source names an employer,
// only one district is measured (#19), the dual-enrolment join is unresearched
// (#42), and the competency gap is open.
