// Education-to-Career Pathways Knowledge Graph — schema
//
// Every shape below earns its place by turning one of the questions in
// docs/questions.md into a traversal. Anything serving none of them is not
// here. The reuse verdict for each external term — adopt, align or mint — is
// docs/ontology-reuse.md; the measured source behind each is docs/sources/.
//
// Two tiers:
//   TIER 1  populated from a source measured by a probe in etl/
//   TIER 2  modelled, not yet populated (source identified but not ingested,
//           or the data provably does not exist yet)
//
// SYNTAX — the `ON (n:L) ASSERT` constraint form is used throughout. The
// Neo4j-5 `CREATE CONSTRAINT <name> IF NOT EXISTS FOR (n:L) REQUIRE` form does
// NOT parse in Samyama-Graph 1.1.0, despite appearing in the engine's
// CYPHER_COMPATIBILITY.md. Do not "modernise" these back.
// tests/test_schema_engine.py executes every statement here against a live
// instance; tests/test_schema_cypher.py checks this file against the documents.
//
// WHAT 1.1.0 DOES AND DOES NOT ACCEPT HERE — measured against the engine, not
// assumed, because each of these is a review reflex from other Cypher engines:
//
//   * NAMES. `CREATE CONSTRAINT course_url ON …` and `CREATE INDEX year_idx ON
//     …` are BOTH parse errors. A constraint here cannot be named, so "name
//     them so a specific one can be replaced later" is not a choice this file
//     is making — it is the only form the parser takes.
//   * DROP. `DROP CONSTRAINT …` is a parse error too, so there is no way to
//     drop or replace one at all. Naming would not have bought anything.
//     `SHOW CONSTRAINTS` does parse, so what is declared can be inspected.
//   * RE-RUNNING IS SAFE. Every statement in this file applied twice against
//     one instance returns no error, so the loader re-applies the schema on
//     each run without a guard. This is asserted in tests/test_schema_engine.py
//     rather than left as a property somebody remembers.
//
// A constraint is a DECLARATION OF THE KEY, not an insert guard — 1.1.0 does
// not reject a duplicate CREATE, measured directly: two `CREATE (:U {k:'same'})`
// against a declared-unique `U.k` both succeed. Loaders must MERGE on the key,
// and nothing but a test enforces that.
//
// =============================================================================
// TIER 1 — uniqueness constraints on populated labels
// =============================================================================

// Course — one published course page in one district's catalogue.
//
// The key is the ABSOLUTE URL of that page, not the course name. This is the
// single most important decision in the file, and it is measured rather than
// assumed: docs/sources/course-prerequisites.md shows the district publishes
// prerequisites as links, so 240 of 240 resolve BY URL. Names do not resolve —
// "Landscaping 1" is a title, and titles collide the moment a second district
// arrives (#19).
//
// This is the same argument as `product_code` in regulatory-affairs-kg: the
// join hub is the identifier the publisher uses, never the display name.
//
// The URL and not the path, because the path does NOT carry the district.
// `etl/probe_pwcs.py` resolves by catalogue-relative path, which is correct
// inside one catalogue and only inside one: /mathematics/algebra-1 is a path
// two districts can both publish. The host is what separates them, so the key
// keeps it. A Course node is not a national concept and must not be merged
// across districts on name or on path — see
// docs/sources/state-course-directories.md, where Texas and New York publish
// entirely different course vocabularies.
//
// NORMALISATION — a key is only unique if everyone spells it the same way, and
// "the absolute URL" is not by itself a spelling. A constraint here DECLARES
// the key and does not enforce it, so nothing catches two nodes for one page;
// the rule has to be written down and followed by every loader.
//
//   scheme        as published, lower-case. The catalogue serves https, and
//                 this is not a place to guess at a redirect.
//   host          lower-cased. DNS is case-insensitive, so Catalog.PWCS.edu
//                 and catalog.pwcs.edu are one host and must not be two keys.
//   path          case PRESERVED. A URL path is case-sensitive by spec;
//                 lower-casing would merge two pages a server may distinguish.
//   trailing "/"  removed. `etl/probe_pwcs.py` already resolves with
//                 `parsed.path.rstrip("/")`, so resolution and the key agree
//                 rather than differing by a character nobody can see.
//   query, "#"    dropped. Neither identifies a different course page here — a
//                 fragment is a position within one page, and a query string
//                 on these pages carries tracking rather than identity.
//
// Applies identically to **Subject.url and Pathway.url** — every label keyed on
// the address of a published page. If a catalogue is ever found that does
// distinguish pages by query string, this rule changes and the reason changes
// with it. It is not a default to be quietly widened.
//
// It is prose because 1.1.0 gives it nowhere else to live: a constraint cannot
// carry a normaliser, and the engine does not enforce uniqueness anyway. The
// one implementation is `etl/pwcs_source.absolute()`, and
// `tests/test_load_pwcs.py` asserts the rule's parts are stated here — so the
// prose cannot drift from the loader without a test noticing.
CREATE CONSTRAINT ON (c:Course) ASSERT c.url IS UNIQUE;

// Programme — a field of study, keyed on its 6-digit CIP code.
// schema:EducationalOccupationalProgram, aligned rather than adopted: ours is
// CIP-coded and US-specific (docs/ontology-reuse.md).
CREATE CONSTRAINT ON (p:Programme) ASSERT p.cip_code IS UNIQUE;

// Occupation — keyed on its SOC code. schema:Occupation, adopted verbatim.
CREATE CONSTRAINT ON (o:Occupation) ASSERT o.soc_code IS UNIQUE;

// Institution — a college or university, keyed on the IPEDS UNITID.
// 6,256 measured. schema:CollegeOrUniversity, aligned: ours is UNITID-keyed and
// will need to cover non-degree providers too (#45).
CREATE CONSTRAINT ON (i:Institution) ASSERT i.unitid IS UNIQUE;

// School and District — the secondary tier, from CCD. 102,268 and 19,714
// measured. Keys are the federal identifiers, not names: district names repeat
// across states.
CREATE CONSTRAINT ON (s:School) ASSERT s.ncessch IS UNIQUE;
CREATE CONSTRAINT ON (d:District) ASSERT d.leaid IS UNIQUE;

// Subject — the catalogue's own grouping ("Agriculture, Food and Natural
// Resources"). Keyed on its absolute URL for the same reason as Course: the
// path alone does not distinguish two districts' catalogues.
CREATE CONSTRAINT ON (sb:Subject) ASSERT sb.url IS UNIQUE;

// Requirement — a condition stated in prose that is NOT a course reference:
// "Enrolled in Agriculture Specialty Program", "Teacher recommendation".
// 138 measured.
//
// Modelled as a NODE rather than as a REQUIRES edge, deliberately. The chosen
// term schema:coursePrerequisites accepts a Course OR free Text, so the
// standard permits both — but a Text is not traversable, and asserting an edge
// to a course that was never named would invent a link the source does not
// make. Keeping it addressable means an unresolved condition survives as data
// instead of being discarded.
//
// This is the same shape as PredicateClaim in regulatory-affairs-kg: the
// unresolved citation is a node, so a truncated chain does not look complete.
//
// id is DETERMINISTIC — sha1("<course URL>|<normalised text>") — so re-running
// the extractor MERGEs rather than duplicating.
//
// "normalised text" means whitespace collapsed to single spaces and the ends
// stripped: `" ".join(text.split())`. Nothing else — no case folding, no
// punctuation removal. The district's wording is the fact being recorded, and
// two conditions differing only in case are two conditions until someone
// measures that they are not.
//
// The course URL, not its path, for the reason Course itself is URL-keyed: a
// path does not carry the district, so "Teacher recommendation" on
// /mathematics/algebra-1 would collide between two districts publishing the
// same path. The key of a dependent node has to be at least as specific as the
// key of the node it depends on.
CREATE CONSTRAINT ON (r:Requirement) ASSERT r.id IS UNIQUE;

// Completion — how many people finished a programme at an institution, at one
// award level, for one demographic group.
//
// IPEDS publishes 9,026,310 such rows: institution x programme x award level x
// demographic x YEAR. That volume is the reason this is a node with a composite
// deterministic key rather than a property bag on an OFFERS edge — the same row
// must MERGE on re-load, and an edge property cannot be keyed.
//
// The year is part of the grain and part of the key. The prose above used to
// list four components while the formula below had five, so the two spellings
// of one key disagreed — and a loader author reading the sentence rather than
// the formula would have merged two years into one node.
//
// id = sha1("<unitid>|<cip_code>|<award_level>|<demographic>|<year>").
// The bounded load (#23) takes a slice; the key is the same either way.
CREATE CONSTRAINT ON (cm:Completion) ASSERT cm.id IS UNIQUE;
CREATE INDEX ON :Completion(year);

// =============================================================================
// TIER 1 — edges
// =============================================================================

// Prerequisite chains — the tier-4 questions, and the reason this is a graph.
// 240 edges measured, every one resolving. Chains of unknown depth are what a
// relational database does badly (docs/questions.md, tier 4).
//   (:Course)-[:REQUIRES]->(:Course)
//
// Adopted from schema:coursePrerequisites. Direction is course -> the thing it
// requires, so "what does skipping this close off" (Q61) is an inbound
// traversal and "what do I need first" (Q65) is outbound.
//
// The condition that is NOT a course reference:
//   (:Course)-[:HAS_REQUIREMENT]->(:Requirement)
//   (:Pathway)-[:HAS_REQUIREMENT]->(:Requirement)
//
// A pathway states conditions too — "Enrolled in Agriculture Specialty
// Program" sits on the programme page, not on any one course in it. Same
// shape, same reason: a condition naming no course is a node, because
// asserting a REQUIRES to a course that was never named would invent a link.

// What a published pathway is made of.
//   (:Pathway)-[:INCLUDES {section, sections, credits}]->(:Course)
//
// 185 edges over 38 pathways, from 202 published rows. The district publishes
// this in a typed field — entity references with a credit value each, grouped
// under named sections like "Web & Digital Communications Pathway" — so it is
// read, not inferred from a page's prose.
//
// `section` carries the district's own grouping, joined with " | " where a
// course appears in more than one. That is a workaround, not a design: an edge
// MERGE in 1.1.0 ignores the property map and matches on start, type and end
// alone, so two edges between one pathway and one course cannot be told apart
// and the second is dropped silently (#77). 17 of the 202 rows are that case.
// `sections` counts how many were folded in, so the collapse is visible in the
// graph rather than only in the loader's output.

// Programme to occupation — the only exact, government-published join between
// education and work. 6,097 mappings over 2,143 programmes and 868 occupations.
// Aligned to ceterms:isPreparationFor, which is broader: theirs reaches
// Occupation, Job and WorkRole, ours only the first.
//   (:Programme)-[:PREPARES_FOR]->(:Occupation)
//
// The crosswalk is a published claim with a revision history, not a fact. Its
// edition lives on the edge (`source_edition`) so Q43 — "the crosswalk is
// revised, which programmes change what they lead to" — is answerable at all.

// Who offers and awards what
//   (:Institution)-[:OFFERS]->(:Programme)
//   (:Completion)-[:AT]->(:Institution)
//   (:Completion)-[:IN]->(:Programme)

// The secondary tier
//   (:School)-[:IN_DISTRICT]->(:District)
//   (:School)-[:TEACHES]->(:Course)
//   (:Course)-[:IN_SUBJECT]->(:Subject)
//
// No edge from Course to Programme. Nothing public links a district course to
// a college programme's entry requirements — docs/questions.md Q39 is marked
// blocked for exactly this reason, and asserting the edge would be the one
// thing this repo has consistently refused to do.

// =============================================================================
// TIER 2 — modelled, not yet populated
// =============================================================================

// Credential — schema:EducationalOccupationalCredential, adopted verbatim.
// The Credential Registry publishes 133,346 of these, but under each
// publisher's own terms rather than the vocabulary's CC BY 4.0 (#56), so
// nothing is loaded until that is settled.
CREATE CONSTRAINT ON (cr:Credential) ASSERT cr.ctid IS UNIQUE;

// Pathway — a published route through courses. TIER 1, and keyed on the URL of
// the page that publishes it, for exactly the reason Course is.
//
// This moved out of tier 2. It was declared here keyed on `ctid`, CTDL's
// identifier, because the Credential Registry was the only publisher in view —
// 98 pathways against 47,861 courses, which is why it was modelled and left
// empty. But a school district publishes pathways too, as pages: PWCS publishes
// 38, sixteen CTE career pathways and twenty-two specialty programs, each with
// its course list in a typed field. Those are loadable today and are loaded.
//
// A district pathway has no ctid. Keeping the ctid key would have given all 38
// nodes a null value for the declared key — which 1.1.0 accepts silently, since
// a constraint here declares the key and does not enforce it. That is the exact
// failure this file warns about two hundred lines further up, and it would have
// shipped.
//
// The Registry's own pathways are still NOT loaded, and when they are they need
// either a distinct label or a composite key carrying the publisher — the shape
// already used for Level (`id = "<body>|<code>"`). Raised as #85 rather than
// decided here on one publisher's evidence.
CREATE CONSTRAINT ON (pw:Pathway) ASSERT pw.url IS UNIQUE;

// -----------------------------------------------------------------------------
// The competency gap — three questions in docs/questions.md are blocked here
// -----------------------------------------------------------------------------
//
// Every awarding body and every learning platform defines its own levels, and
// none publishes what a level MEANS in competency terms. A pass mark advances a
// student in one system and not in another. No crosswalk between them exists.
//
// The shape below is the answer this repo has already used twice — for CIP-SOC
// and for CTDL — rather than a new invention:
//
//   * a Level BELONGS TO its issuing body. There is no free-floating "grade 8".
//   * an equivalence between two bodies' levels is a CLAIM WITH A SOURCE, not a
//     fact. It is an edge carrying who asserted it, so a reader can disagree.
//   * where no crosswalk exists, the graph says nothing. It does not infer one
//     from names that happen to match.
//
// This is why Level is keyed on (body, code) and why EQUIVALENT_TO is not a
// plain edge. Asserting an unpublished equivalence is exactly the error this
// repo refused with Submission -> MarketedDevice in regulatory-affairs-kg.

// AwardingBody — who issues a level.
//
// id = "<publisher scheme>|<body identifier>". The body's own published
// identifier where it has one, else "slug|<kebab-cased name>". The scheme is
// carried because two registers can issue the same identifier, which is the
// same reason Level and Competency are composite.
//
// Tier 2 and unpopulated, so this is a shape rather than a measured decision.
// The first body loaded settles it, and the reason it is composite goes here
// so that choice is not reopened.
CREATE CONSTRAINT ON (ab:AwardingBody) ASSERT ab.id IS UNIQUE;

// Level — a named step in one body's scheme.
//
// id = "<awarding body id>|<level code>", so the same label under two bodies
// cannot collide.
//
// **The separator does not nest.** `AwardingBody.id` is itself
// "<scheme>|<body>", so a Level id is "<scheme>|<body>|<level code>" and
// "a|b|c" has two readings: body "a|b" with level "c", or body "a" with level
// "b|c". Splitting on "|" therefore recovers the wrong parts, which matters
// the moment anything reads an id back rather than only writing it.
//
// The rule: a Level id is built by APPENDING one separator to the awarding
// body's id, and it is parsed by splitting from the RIGHT exactly once —
// `body, _, code = id.rpartition("|")`. The level code is the only component
// guaranteed free of the separator, and the body id keeps whatever internal
// structure it has. The same rule applies to Competency, which embeds a
// framework id the same way. Nothing enforces this but this note and the
// loader that will first write one; tier 2, so no loader has yet.
CREATE CONSTRAINT ON (lv:Level) ASSERT lv.id IS UNIQUE;

// id = "<framework id>|<competency code>", the same shape as Level and for the
// same reason: a competency belongs to the framework that defines it, and two
// frameworks reusing a code — "1.2", "K.CC.1" — are two competencies. There is
// no free-floating competency here any more than there is a free-floating
// level. Tier 2 and unpopulated, so this is a shape rather than a measured
// decision; the first framework loaded settles the spelling of the framework
// id, and the reason it is composite goes here so that choice is not reopened.
CREATE CONSTRAINT ON (cp:Competency) ASSERT cp.id IS UNIQUE;

//   (:Level)-[:ISSUED_BY]->(:AwardingBody)
//   (:Level)-[:EQUIVALENT_TO {asserted_by, source_url}]->(:Level)
//
// EQUIVALENT_TO is DIRECTED and NOT symmetric, deliberately. The edge records
// that one body asserted an equivalence, and the assertion has a direction:
// body A publishing "our level 4 equals their level 3" is a different fact
// from body B publishing the converse, and only one of them may exist.
//
// So a query asking "what is equivalent to this level" must traverse both
// directions — MATCH (a:Level)-[:EQUIVALENT_TO]-(b:Level) — and a loader must
// NOT helpfully write the reverse edge, because that would assert something
// nobody published. This is the same refusal as the rest of the file, applied
// to the direction of a claim rather than to its existence.
//
// UNIQUENESS IS NOT ENFORCED, and cannot be. 1.1.0 constrains node properties
// only — there is no relationship constraint to declare — so nothing stops the
// same equivalence being written twice, once per load. The identity of the
// edge is (start level, end level, asserted_by): one body may assert a given
// equivalence once. A loader MUST therefore MERGE on all three and never
// CREATE, exactly as the node loaders must, and this line is the only thing
// enforcing it. Duplicated, the edge does not corrupt a traversal — but any
// query that COUNTS equivalences returns a load count rather than a fact.
//   (:Course)-[:DEVELOPS]->(:Competency)
//   (:Level)-[:EXPECTS]->(:Competency)

// -----------------------------------------------------------------------------
// Earnings and outlook — named but not counted
// -----------------------------------------------------------------------------
//
// docs/sources/education-data.md lists BLS, O*NET and College Scorecard under
// "named but not counted": no probe measures them yet (#37, edtech-kg#21 —
// this repo's tracker, not samyama-graph#21, which docs/schema.md also
// cites and which is a different issue in a different repository). Fifteen
// questions depend on them, so the shapes are declared and left empty rather
// than the questions being quietly dropped.
//
// EarningsRecord is a node, not a property on Occupation, because the figure is
// per cohort and per year and revises — Q55 asks which rankings move when it
// does.
//
// The subject is named by kind and id rather than described. An earlier
// spelling read "<what it is about>", which is a description a loader cannot
// implement — and the two edges below already say the figure is about exactly
// one of an occupation or a programme.
//
// The same composite shape as Completion, for the same reason: several
// publishers report earnings for overlapping populations, and a row from
// College Scorecard is not a row from BLS even where both name the same
// occupation and year. Tier 2; the components firm up when the first source
// is loaded (edtech-kg#21, #37).
//
// id = sha1("<subject kind>|<subject id>|<cohort>|<year>|<source>"), where
// subject kind is "occupation" or "programme" and subject id is its SOC or
// CIP code.
CREATE CONSTRAINT ON (er:EarningsRecord) ASSERT er.id IS UNIQUE;
CREATE INDEX ON :EarningsRecord(year);

//   (:EarningsRecord)-[:FOR_OCCUPATION]->(:Occupation)
//   (:EarningsRecord)-[:FOR_PROGRAMME]->(:Programme)

// -----------------------------------------------------------------------------
// Geography — "near me" needs this to be true (#44)
// -----------------------------------------------------------------------------
// id = "<kind>|<published identifier>" — "state|VA", "cbsa|47900",
// "county|51153". Not "federal identifier": the state example is a USPS postal
// abbreviation, not the FIPS code (Virginia is FIPS 51), and calling all three
// federal invited a loader author to look for a number that is not what the
// example shows. The kind is carried because a bare code is not unique across
// kinds — 51 is Virginia as a state FIPS and something else as a county. Tier 2 and blocked on #44, which is the question of
// what "near me" has to mean before any of this is worth loading.
CREATE CONSTRAINT ON (pl:Place) ASSERT pl.id IS UNIQUE;

//   (:Institution)-[:LOCATED_IN]->(:Place)
//   (:District)-[:LOCATED_IN]->(:Place)

// =============================================================================
// What this schema does NOT claim
// =============================================================================
//
// Written down before anyone finds it, which is the house standard.
//
// 1. NO student. Individual student records are permanently out of scope
//    (docs/scope.md §1). Nothing here can answer "where is this child".
//
// 2. NO national prerequisite graph. REQUIRES is populated for ONE district,
//    795 courses, drawn from a 960-page sitemap — 960 is the page count, not
//    the course count, and docs/schema.md carries the correction (#74).
//    #40 measured that statewide directories publish none at all,
//    so this is a property of one publisher's catalogue software, not of US
//    education data. #19 asks whether a second district resolves as cleanly.
//
// 3. NO Course -> Programme edge. See above: no public source links them.
//
// 4. NO inferred competency equivalence. See the competency gap.
//
// 5. Completions are counts, not people. A Completion is a published
//    aggregate; it cannot be traversed back to anyone.
//
// 6. PREPARES_FOR is a published claim, not causation. The crosswalk says a
//    programme prepares for an occupation. It does not say graduates get those
//    jobs, and no data here supports that reading.
