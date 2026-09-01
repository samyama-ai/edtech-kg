// Tier 4 — graph algorithms. The tier `docs/questions.md` calls "the reason to
// use a graph", and the one this exercise most needed to check.
//
// edtech-kg#22. These PARSE against the engine. The prerequisite edges are
// loaded for one district, so unlike the other tiers most of these run against
// real data rather than an empty label.
//
// What the engine has, measured rather than assumed: variable-length paths
// bounded and unbounded, `shortestPath`, `allShortestPaths`, `length()`,
// `nodes()`, `relationships()`, and `NOT x IN nodes(p)` inside a nested
// `NOT EXISTS`. What it does not have: GDS (`Unknown procedure`), `count{}`,
// `size(pattern)`, and `UNWIND` as a leading clause.
//
// Two questions in this tier cannot be answered and are re-marked, with the
// reasons in `docs/questions.md`. Neither is a gap in the engine.

// Q61. If I skip chemistry this year, what does that close off later?
// The blast radius, and the same closure as Q49 asked from the student's side.
MATCH (closed:Course)-[:REQUIRES*]->(:Course {url: "https://catalog.pwcs.edu/science/chemistry-1"})
RETURN DISTINCT closed.url, closed.name;

// Q62. What is the shortest route from where I am now to this programme?
// Course to course, which is what "route" means inside a catalogue. See the
// note on Q75: there is no academic edge from a district course to a
// post-secondary programme, so "to this programme" cannot be walked — and the
// question is re-marked ⚠️ in docs/questions.md for that reason, rather than
// leaving the justification here where the status table cannot see it.
// Both endpoints need a VARIABLE — `shortestPath` on this engine refuses an
// anonymous target ("shortestPath target must have a variable"), which is not
// a Cypher rule and is worth knowing before writing fifteen of these.
MATCH p = shortestPath(
  (a:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-4"})
  -[:REQUIRES*]->(b:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-1"}))
RETURN length(p) AS steps, [n IN nodes(p) | n.url] AS route;

// Q63. I'm in year 11 and I've taken these five courses. What am I still missing?
// A set difference: everything the target needs, less what is done. The taken
// list is a parameter in practice; it is inline here because this engine takes
// no query parameters — `/api/query` accepts a query and a graph, nothing else.
MATCH (:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-4"})-[:REQUIRES*]->(needed:Course)
WHERE NOT needed.url IN [
  "https://catalog.pwcs.edu/agriculture/landscaping-1",
  "https://catalog.pwcs.edu/agriculture/landscaping-2"]
RETURN DISTINCT needed.url, needed.name;

// Q64. I was heading for accounting, now I want data analysis. What carries over?
// The INTERSECTION of two ancestor sets — what both routes already required.
MATCH (:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-4"})-[:REQUIRES*]->(shared:Course)
MATCH (:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-6"})-[:REQUIRES*]->(shared)
RETURN DISTINCT shared.url, shared.name;

// Q65. I want to be a nurse. What do I take next semester?
// The FRONTIER: needed, and every prerequisite of it already done. Written as
// "no unmet prerequisite outside the completed list", which is what makes it
// takeable now rather than merely needed eventually.
MATCH (:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-4"})-[:REQUIRES*]->(needed:Course)
WHERE NOT needed.url IN ["https://catalog.pwcs.edu/agriculture/landscaping-1"]
  AND NOT EXISTS {
    MATCH (needed)-[:REQUIRES]->(unmet:Course)
    WHERE NOT unmet.url IN ["https://catalog.pwcs.edu/agriculture/landscaping-1"]
  }
RETURN DISTINCT needed.url, needed.name;

// Q66. How deep does the deepest prerequisite chain run?
MATCH p = (:Course)-[:REQUIRES*]->(:Course)
RETURN max(length(p)) AS deepest_chain;

// Q67. Which courses are unreachable from any entry point?
// ISOLATED, which is the data-quality reading: a course with no prerequisite
// and nothing requiring it is outside every chain rather than at the start of
// one. 431 of 791 stand outside every chain — say that before being asked.
MATCH (c:Course)
WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->(:Course) }
  AND NOT EXISTS { MATCH (:Course)-[:REQUIRES]->(c) }
RETURN count(c) AS outside_every_chain;

// Q68 is re-marked ❌ and has no query. It asked which single course, if
// removed, disconnects the most others — articulation points.
//
// A previous round claimed this WAS expressible: a cut vertex for a pair is a
// node on every path between them, and `NOT x IN nodes(p)` inside a nested
// `NOT EXISTS` says so. It parses. It also runs without error. And it is
// wrong, which is worse than either.
//
// Measured against the loaded district — 240 REQUIRES edges, 119 chains of
// length 2 or more, so cut vertices certainly exist:
//
//     MATCH p=(a:Course)-[:REQUIRES*2..]->(b:Course) MATCH (x:Course)
//     WHERE     x IN nodes(p)  RETURN count(*)   ->  0
//     WHERE NOT x IN nodes(p)  RETURN count(*)   ->  0
//
// BOTH are zero. `IN` over a list of nodes is not usable here, and rather than
// refusing it matches nothing either way — so the query returns "there are no
// articulation points" on a graph that has them. A confident wrong answer.
//
// The earlier claim was made on PARSING alone, against an engine holding no
// data, where a predicate inside a WHERE is never evaluated. That is the gap
// this whole exercise exists to close, and it caught me in the file where the
// argument is made.
//
// It stays unanswered rather than approximated: `count(DISTINCT …)` over
// prerequisite counts would rank courses by something, and it would not be
// articulation points.

// Q69. What is the full ancestor set of this course?
MATCH (:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-4"})-[:REQUIRES*]->(a:Course)
RETURN DISTINCT a.url, a.name;

// Q70. What is its full descendant set — everything it unlocks?
MATCH (d:Course)-[:REQUIRES*]->(:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-1"})
RETURN DISTINCT d.url, d.name;

// Q71. Are there cycles in the prerequisite graph?
// A cycle is a PUBLISHING ERROR — a course requiring itself transitively can
// never be taken — so finding none is the answer worth having. Bounded at 10:
// an unbounded walk over a cycle does not terminate.
MATCH p = (c:Course)-[:REQUIRES*1..10]->(c)
RETURN c.url, length(p) AS cycle_length;

// Q72. Which two courses are furthest apart in the prerequisite graph?
// The DIAMETER — the longest shortest path, which is not the longest path.
MATCH p = shortestPath((a:Course)-[:REQUIRES*]->(b:Course))
WITH a, b, length(p) AS distance
RETURN a.url, b.url, distance ORDER BY distance DESC LIMIT 5;

// Q73. How many distinct prerequisite chains lead to this course?
// Every path, not every ancestor. A course reachable by two routes is one
// ancestor and two chains, and the difference is the question.
MATCH p = (:Course)-[:REQUIRES*]->(:Course {url: "https://catalog.pwcs.edu/agriculture/landscaping-1"})
RETURN count(p) AS chains;

// Q74. Which courses sit on the most paths between others?
// BETWEENNESS, counted over paths rather than normalised. Like Q68 this is a
// REPORT rather than an interactive query: it enumerates every path in the
// graph, which is exponential in a dense one and merely large here. Say so
// before someone runs it against a national graph and concludes the engine
// hung. `UNWIND` does not
// parse as a leading clause on this engine but does after a `MATCH`, which is
// all this needs.
MATCH p = (:Course)-[:REQUIRES*]->(:Course)
UNWIND nodes(p) AS on_path
RETURN on_path.url, on_path.name, count(*) AS paths_through
ORDER BY paths_through DESC LIMIT 10;

// Q76. Which entry-level courses open the most downstream options?
// ENTRY-LEVEL is the definition doing the work: a course with no prerequisite
// of its own. Ranked by how many courses eventually require it.
MATCH (d:Course)-[:REQUIRES*]->(entry:Course)
WHERE NOT EXISTS { MATCH (entry)-[:REQUIRES]->(:Course) }
RETURN entry.url, entry.name, count(DISTINCT d) AS opens
ORDER BY opens DESC LIMIT 10;

// Q77. Is this programme reachable from this school's course offering at all?
// Answered as the COURSE side only, for the reason in Q75: the only route from
// a course to a programme runs through Place, which is geography. What is
// answerable is whether the school teaches the chain a course sits on.
MATCH (:School {ncessch: "510126000341"})-[:TEACHES]->(taught:Course)
MATCH p = (taught)-[:REQUIRES*]->(root:Course)
WHERE NOT EXISTS { MATCH (root)-[:REQUIRES]->(:Course) }
RETURN DISTINCT taught.url, root.url, length(p) AS depth;

// Q79. Which prerequisite chains cross subject boundaries?
// The finding this asks for is whether a catalogue's subjects are silos. A
// chain starting in one subject and ending in another is the counter-example.
MATCH p = (a:Course)-[:REQUIRES*]->(b:Course)
MATCH (a)-[:IN_SUBJECT]->(sa:Subject)
MATCH (b)-[:IN_SUBJECT]->(sb:Subject)
WHERE sa.url <> sb.url
RETURN sa.name, sb.name, count(p) AS chains ORDER BY chains DESC LIMIT 10;

// Q75 and Q78 are re-marked ❌ by #22 and have no query. Q80 was already ❌.
//
// Q75 asked for the shortest course sequence reaching a programme. There is NO
// academic edge from a district Course to a Programme: the only route in the
// schema is Course <-TEACHES- School -IN_DISTRICT-> District -LOCATED_IN->
// Place <-LOCATED_IN- Institution -OFFERS-> Programme, which says "a college
// in the same state offers this" and not "this course prepares you for it".
// A traversal would return a geographic path and read as an academic answer.
// That join is #66, and it is the gap the whole graph is missing.
//
// Q78 asked for the minimum set of courses covering the most pathways. Set
// cover is an optimisation over the graph rather than a traversal of it — the
// data is all here and the operation is not Cypher. The greedy first step is
// expressible and is a different question, so it is not written here as though
// it were an answer to this one.
