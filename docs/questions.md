# The questions this graph must answer

Written before any ontology, in the language the asker uses — not in the shape
of the data. Every node and edge in the schema has to earn its place by turning
one of these into a single traversal. Anything serving none of them stays out.

This mirrors how `regulatory-affairs-kg` was built: 17 questions first, schema
second. It is also how the honest limits surface early — several questions
below cannot be answered from public data, and saying so now is cheaper than
discovering it after a loader exists.

**Status key**

| | |
|---|---|
| ✅ | answerable from data measured on 2026-08-13 |
| ⚠️ | answerable, but with a caveat that must be stated in the answer |
| ❌ | needs data we do not have and may not be able to get |

---

## A. The student's own path

**Q1. I want to be a nurse. What do I take next semester?** ❌
The question the product exists for. Needs course-level prerequisites, which
are not published — they live in each district's student information system.
This is the single unknown that decides whether the demo is prerequisite chains
or something else.

**Q2. I'm in year 11 and I've taken these five courses. What am I still missing
for this programme?** ❌
Same blocker as Q1. A set-difference over a prerequisite graph.

**Q3. If I skip chemistry this year, what does that close off later?** ❌
The blast-radius question — structurally identical to *"this regulation changed,
which devices are affected?"* in the FDA graph. It is the strongest graph story
here and the least available data.

**Q4. What is the shortest route from where I am now to becoming a radiologic
technologist?** ❌
Shortest-path over prerequisites plus programme requirements. Graph-native, and
gated on the same missing data.

**Q5. I've changed my mind — I was heading for accounting, now I want data
analysis. What carries over?** ❌
Overlap between two prerequisite sets.

## B. Programme to occupation

**Q6. This degree programme — what jobs does it actually lead to?** ✅
The CIP-SOC crosswalk: 6,097 official mappings published jointly by NCES and
the Bureau of Labor Statistics. This is the exact-join backbone, the equivalent
of `regulation_number` in the device graph.

**Q7. I want this job. Which programmes lead to it?** ✅
The same edge traversed backwards. 868 SOC codes are covered.

**Q8. What does that job actually pay, and is it growing or shrinking?** ✅
O\*NET and BLS occupation data, public and free.

**Q9. How many people graduated in this programme last year, nationally?** ✅
IPEDS completions — 9,026,310 records for 2022 alone, by institution ×
programme × award level.

**Q10. Is this programme oversupplied — more graduates than the occupation
hires?** ⚠️
Both halves are public, but the join is a comparison of two independently
collected series. Directional, not a labour-market forecast, and the answer
must say so.

**Q11. Which occupations can be reached from the most different programmes?** ✅
Pure graph — degree of a node in the crosswalk. Useful for "what keeps my
options open".

**Q12. Which programmes are dead ends — mapping to only one occupation?** ✅
The inverse, and a more useful counselling question than it first looks.

## C. Institutions

**Q13. Which colleges near me offer this programme?** ✅
IPEDS completions carry institution and programme. 6,256 institutions measured.

**Q14. Of those, which actually graduate people in it — rather than listing
it in a catalogue?** ✅
Completions are counts of awards conferred, so this distinguishes a real
programme from a nominal one. A genuinely good question that a course catalogue
cannot answer.

**Q15. What does it cost, and what do graduates earn afterwards?** ⚠️
College Scorecard publishes both. Earnings are for federal-aid recipients only,
so the cohort is not all graduates — that caveat travels with every answer.

**Q16. Which institutions award this programme at which levels — certificate,
associate, bachelor's?** ✅
IPEDS award levels.

## D. The school system side

**Q17. Which high schools feed this district's students into this programme?** ❌
No public dataset links a school to its graduates' college programmes.

**Q18. How many schools and districts are we talking about?** ✅
102,268 public schools and 19,714 districts, measured.

**Q19. Which districts have no school offering a pathway into the fastest-
growing occupations?** ⚠️
Answerable only if district course offerings can be obtained. Falls with Q1.

## E. Change and impact — the queries a graph is for

**Q20. The CIP-SOC crosswalk is revised. Which programmes change what they lead
to, and which students are affected?** ✅ / ❌
The first half is answerable and is the direct analogue of the FDA
change-impact query. The second half needs student data we will not hold.

**Q21. An occupation's outlook is downgraded. Which programmes feed it, and how
many people are currently enrolled in them?** ✅

**Q22. A programme is discontinued at an institution. What was it feeding?** ✅

**Q23. This occupation now requires a licence. Which programmes lead to it, and
do they prepare for that licence?** ⚠️
First half yes; licensure requirements are state-by-state and not centrally
published.

## F. Equity and access — where the data is strongest

**Q24. Which programmes have the widest gap between who enrols and who
completes?** ✅
IPEDS reports completions by demographic. Real, measured, and the kind of
question that makes an edtech product worth funding.

**Q25. Are high-earning occupations reachable from programmes offered in
low-income districts?** ⚠️
Needs the district-offering link from Q1's family, but a weaker version —
institution-level rather than course-level — is answerable today.

**Q26. Which occupations pay above median but need only a certificate or
associate degree?** ✅
Two public joins, entirely answerable, and probably the single most useful
answer in this whole list for a student who cannot afford four years.

---

## What this tells us before we design anything

**Fourteen of the twenty-six are answerable as they stand**, five more with a
caveat that has to travel with the answer, and one (Q20) is half answerable.
Six are blocked outright.

| | Count |
|---|---:|
| ✅ answerable today | 14 |
| ⚠️ answerable, caveat required | 5 |
| ✅/❌ partly answerable | 1 |
| ❌ blocked | 6 |

The answerable ones cluster on one side — programme → occupation → earnings,
plus institutions and completions. All of it rests on the CIP-SOC crosswalk,
the one exact government-published join.

**Everything in section A is blocked on the same missing data** — course-level
prerequisites. That is not a coincidence: the questions a student most wants
answered are exactly the ones no public dataset supports. It is the same shape
as the FDA predicate device, which lives only inside a PDF.

So the demo is one of two things, and it is not our choice to make yet:

- **If one real district's catalogue with prerequisites can be obtained** —
  prerequisite chains, and section A becomes the story.
- **If not** — Q6, Q8, Q26 and Q24: programme → occupation → earnings, with
  equity gaps. Weaker as a graph story, entirely public, and defensible today.

**Answering that question comes before the ontology.** Designing for
prerequisites we cannot load would repeat the predicate-chain mistake — a
beautiful shape with nothing in it.

Three questions are worth keeping even though we cannot answer them (Q1, Q3,
Q17). They are the ones that justify the graph if the data ever arrives, and
recording them now is how the ontology avoids needing a redesign later.
