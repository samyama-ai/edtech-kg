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

// Pathway — a published route through courses, keyed on the URL of the page
// that publishes it, for exactly the reason Course is.
//
// This moved out of tier 2. It was declared keyed on `ctid`, CTDL's
// identifier, because the Credential Registry was the only publisher in view —
// 98 pathways against 47,861 courses, which is why it was modelled and left
// empty. A school district publishes pathways too, as pages: 42 load from
// PWCS, and none carries a ctid, so that key would have given all 42 a null
// value — which 1.1.0 accepts in silence, since a constraint here declares the
// key and does not enforce it.
//
// #85 asked what the second publisher then needs. Measured, not argued: all 98
// Registry pathways read — `ctid` fits 98/98, `subjectWebpage` leaves 20 nulls
// AND merges 7 onto 4 shared pages. Neither publisher's key fits both, so
// `Pathway.id = "<space>|<identifier>"`, space one of "url" or "ctid" — the
// shape AwardingBody, Level and Competency use, but PARSED FROM THE LEFT, the
// opposite of Level, because here the LEADING component is the one free of "|"
// and a URL is not; Level's `rpartition` would recover the wrong parts.
// The constraint still names `url` and moves to `id` when a loader first
// writes one — Registry work, blocked on #56; declaring it now would declare a
// key no loader writes. Reasoning: docs/sources/pathway-identity.md.
CREATE CONSTRAINT ON (pw:Pathway) ASSERT pw.url IS UNIQUE;

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
//   (:Pathway)-[:INCLUDES {section, sections, rows, credits}]->(:Course)
//
// 316 edges over 42 pathways, from 374 published rows. The district publishes
// this in a typed field — entity references with a credit value each, grouped
// under named sections like "Web & Digital Communications Pathway" — so it is
// read, not inferred from a page's prose.
//
// `section` carries the district's own grouping, joined with " | " where a
// course appears in more than one. That is a workaround, not a design: an edge
// MERGE in 1.1.0 ignores the property map and matches on start, type and end
// alone, so two edges between one pathway and one course cannot be told apart
// and the second is dropped silently (#77). 58 of the 374 rows are that case.
// `rows` counts how many published rows folded into the edge, so the collapse
// is visible in the graph rather than only in the loader's output. `sections`
// is how many NAMED sections it covers, which is what `section` joins — the
// two differ the moment two rows share a section or a row carries none, and
// `sections` alone was being read as the row count it is not.

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
