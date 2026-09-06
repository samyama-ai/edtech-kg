// Education-to-Career Pathways Knowledge Graph — schema, tier 2
//
// MODELLED, NOT YET POPULATED. Every constraint here declares a key for a label
// no loader writes: the source is identified but not ingested, or the data
// provably does not exist yet. Tier 1 — everything actually populated from a
// measured source — is in `edtech_kg.cypher`, and the syntax notes that govern
// both files are there too.
//
// Split out at 499 lines of the 500-line review ceiling (#157). Six reviews in
// this repo have reported a file as too large and read nothing inside it, and
// the file that would have been skipped is the one declaring every key in the
// graph. #85 was already written tight against that ceiling — the measured
// reasoning behind the Pathway key was moved to docs/sources/ and only the
// verdict left inline. That was the right split, but it was forced.
//
// The cut is by SUBJECT, not by line count, following #86 (registry_read out of
// probe_registry) and tests/test_dead_code_channels.py. Tier 1 and tier 2 are
// already this schema's own organising idea and already how docs/schema.md
// reads. A cut at the midpoint would have put keys in one file and the rule
// that normalises them in another.
//
// **A key declared here is a claim about shape, not about data.** Nothing below
// is populated, so none of it has been tested against real values — which is
// the distinction tier 2 exists to keep visible. Both files are applied
// together by `etl/cypher_script.py` and executed against a live instance by
// tests/test_schema_engine.py; neither is optional.

// =============================================================================
// TIER 2 — modelled, not yet populated
// =============================================================================

// Credential — schema:EducationalOccupationalCredential, adopted verbatim.
// The Credential Registry publishes 133,346 of these, but under each
// publisher's own terms rather than the vocabulary's CC BY 4.0 (#56), so
// nothing is loaded until that is settled.
CREATE CONSTRAINT ON (cr:Credential) ASSERT cr.ctid IS UNIQUE;

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
//    791 courses, drawn from a 960-page sitemap — 960 is the page count, not
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


// -----------------------------------------------------------------------------
// Attributes — edtech-kg#123
// -----------------------------------------------------------------------------
// Every constraint above declares a KEY. Until now the schema declared nothing
// else, so a traversal naming `o.name` on an Occupation parsed, returned null,
// and looked like an answer — and #22 found fifteen of those across the six
// tiers. `Q2. What occupation does this SOC code name?` is entirely the name,
// and the schema promised only the code.
//
// Each line below is `Label.property <- the field a source publishes it as`.
// The source field is the point: a property with no field behind it is a wish,
// and the whole reason for this section is that a reader can check the
// commitment rather than trust it.
//
// WHAT IT DOES NOT SAY IS THAT ANYTHING WRITES THEM. Measured: `load_pwcs.py`
// is the only loader here and it writes Course, Pathway, Requirement and
// Subject. Nothing loads Occupation, Programme, Institution, School, District
// or Completion, and `SOC2018Title`, `INSTNM`, `school_name` and `lea_name`
// appear in no loader at all. So `o.name` still returns null, and the `NEEDS:`
// annotation on every such query stays until a loader lands — see
// `tests/schema_properties.declared`, which reads the CONSTRAINTS and the
// LOADERS and deliberately not this block. The first attempt at #123 read it
// as reachability and dropped 33 of those annotations.
//
// Two entries name a file; the rest name a published dataset and its column,
// because this repo has no downloader for them and inventing a filename would
// be the same wish this section refuses.
//
// PROPERTIES
//   Occupation.name        <- CIP2020_SOC2018_Crosswalk.xlsx, SOC2018Title
//   Programme.name         <- CIP2020_SOC2018_Crosswalk.xlsx, CIP2020Title
//   Institution.name       <- IPEDS HD, INSTNM
//   Institution.control    <- IPEDS HD, CONTROL
//   School.name            <- CCD school directory, school_name
//   District.name          <- CCD district directory, lea_name
//   Completion.awards      <- IPEDS C, CTOTALT
//   Completion.award_level <- IPEDS C, AWLEVEL
//   Course.description     <- catalog.pwcs.edu, field--name-field-description
//   Course.grade_levels    <- catalog.pwcs.edu, field--name-field-grades
// END PROPERTIES
//
// TWO OF THE TEN ARE NOW WRITTEN. `etl/load_pwcs.py` extracts
// `Course.description` and `Course.grade_levels` from the course page
// (edtech-kg#137): 783 of 791 courses carry a description, 781 carry grades.
// Q9 and Q14 lost their `NEEDS:` lines, which is the point of the annotation —
// it comes off when a loader lands, not when someone remembers. The other
// eight stay named-only, and not because `Course` is special: nothing loads
// Occupation, Programme, Institution, School, District or Completion at all.
//
// NOT declared, and each for its own reason:
//
//   Course.length — no source publishes it. The catalogue carries
//   `field-credits` and `field-grades` and no length or duration field at all,
//   so Q9's "grade levels and length" is answerable in one half. Declaring a
//   property to satisfy a question is how a schema starts describing what
//   somebody wanted rather than what anyone publishes.
//
//   EarningsRecord.median, .year, .source, .employment — no loader exists and
//   the key's own note above says the components firm up when the first source
//   is loaded (#21, #37). Declaring them now would fix a shape before anything
//   has been read, which is the mistake `Pathway` already made once when it
//   was keyed on `ctid` and left empty.
//
// Award level is the one attribute anything FILTERS on — `Q25`, `Q32`, `Q85`
// and `Q91` all select by it — so it is the one that earns an index. The rest
// are returned, not searched, and indexing them would claim a lookup pattern
// this graph does not have.
CREATE INDEX ON :Completion(award_level);

