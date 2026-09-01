// Tier 5 — multi-domain. A question crossing from one source into another.
//
// edtech-kg#22, and the tier where the exercise found the most. TEN of the
// fourteen cannot be answered, and nine of those trace to one cause rather
// than to nine: **there is no academic edge from a district Course to a
// Programme or an Occupation.** The only route in the schema runs through
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
//   NEEDS: EarningsRecord.median, Occupation.name
//   The POST-SECONDARY half only. "Low-income district" is a school-side fact
//   and joins to a Place, not to a programme, so this answers what a Place's
//   institutions reach and at what earnings — leaving the income measure to a
//   caller who has one.
MATCH (:Place {id: "state|VA"})<-[:LOCATED_IN]-(i:Institution)-[:OFFERS]->(p:Programme)
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
MATCH (er:EarningsRecord)-[:FOR_OCCUPATION]->(o)
RETURN DISTINCT o.soc_code, o.name, er.median ORDER BY er.median DESC;

// Q85. Which occupations pay above median but need only a certificate?
//   [caveat: award level is what a programme confers, not what an occupation requires]
//   NEEDS: Completion.award_level, EarningsRecord.median, Occupation.name
//   The distinction Q32 also turns on, and it is the whole caveat: this finds
//   occupations reachable from programmes AWARDED at certificate level. What
//   an occupation REQUIRES is not published anywhere this graph reads.
MATCH (cm:Completion {award_level: "Certificate"})-[:IN]->(p:Programme)
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
MATCH (er:EarningsRecord)-[:FOR_OCCUPATION]->(o)
RETURN DISTINCT o.soc_code, o.name, er.median ORDER BY er.median DESC;

// Q86. Is this programme oversupplied — more graduates than the occupation absorbs?
//   [caveat: completions are measured, absorption is not]
//   NEEDS: Completion.awards, Occupation.name
//   Half a question, and the half that exists is the supply. Nothing published
//   here says how many an occupation absorbs, so the ratio the question wants
//   cannot be computed — only its numerator.
MATCH (cm:Completion)-[:IN]->(p:Programme {cip_code: "11.0101"})
MATCH (p)-[:PREPARES_FOR]->(o:Occupation)
RETURN o.soc_code, o.name, sum(cm.awards) AS graduates_supplied;

// Q91. Which institution offers the most efficient route to this occupation?
//   [caveat: efficiency here is award level, not time or cost — neither is held]
//   NEEDS: Completion.award_level, Institution.name
//   EFFICIENT is doing a lot of work in the question. What is measurable is
//   the award level a programme reaching the occupation is conferred at; a
//   certificate is a shorter route than a bachelor's, and that ordering is the
//   answer this graph can give.
MATCH (i:Institution)-[:OFFERS]->(p:Programme)-[:PREPARES_FOR]->(:Occupation {soc_code: "29-1141"})
MATCH (cm:Completion)-[:AT]->(i)
MATCH (cm)-[:IN]->(p)
RETURN DISTINCT i.unitid, i.name, cm.award_level;

// Ten have no query. Nine are one cause.
//
// Q81, Q83, Q89 and Q90 ask a district question about occupations, and Q75 in
// tier 4 asks the same thing from the other side. All four need a Course to
// reach a Programme or an Occupation academically, and it cannot: the walk
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
