// Tier 6 — whole-graph structure. What the graph looks like, not what is in it.
//
// edtech-kg#22. These run against the loaded prerequisite graph rather than an
// empty label, so unlike most of the other tiers they return real answers
// today. All eight are answerable and all eight are written — Q95 in two
// statements, because "how many components" has no component procedure here
// and the isolated count and the linked count are the two halves of it.

// Q95. What does the prerequisite graph look like — how many components?
// COMPONENTS without a component algorithm: a course outside every chain is
// its own component, and the rest form connected groups. This reports the
// isolated count and the linked count, which is the shape of the answer the
// question wants. The two counts below ARE the figures; typing them into
// this comment as well is how the last stale number in this repo got there.
MATCH (c:Course)
WHERE NOT EXISTS { MATCH (c)-[:REQUIRES]->(:Course) }
  AND NOT EXISTS { MATCH (:Course)-[:REQUIRES]->(c) }
RETURN count(c) AS isolated;

MATCH (c:Course)-[:REQUIRES]->(:Course)
RETURN count(DISTINCT c) AS in_a_chain;

// Q96. Which subject areas are most internally connected?
// INTERNALLY: both ends of the edge in the same subject. A subject whose
// courses require each other is a sequence; one whose courses require courses
// elsewhere is a collection of entry points.
MATCH (a:Course)-[:REQUIRES]->(b:Course)
MATCH (a)-[:IN_SUBJECT]->(s:Subject)
MATCH (b)-[:IN_SUBJECT]->(s)
RETURN s.name, count(*) AS internal_edges ORDER BY internal_edges DESC;

// Q97. Which occupations are hubs in the crosswalk?
// Degree centrality, which is a count of edges and needs no algorithm.
MATCH (:Programme)-[:PREPARES_FOR]->(o:Occupation)
RETURN o.soc_code, count(*) AS degree ORDER BY degree DESC LIMIT 20;

// Q98. Are there communities of programmes that share occupations?
// COMMUNITY DETECTION has no procedure on this engine, so this reports the
// relation the algorithm would cluster over: pairs of programmes sharing an
// occupation, and how many they share. That is the input to clustering rather
// than the clustering, and saying so is better than implying otherwise.
MATCH (a:Programme)-[:PREPARES_FOR]->(o:Occupation)<-[:PREPARES_FOR]-(b:Programme)
WHERE a.cip_code < b.cip_code
RETURN a.cip_code, b.cip_code, count(o) AS shared
ORDER BY shared DESC LIMIT 20;

// Q99. Which nodes are most central to the whole graph?
// Degree over the prerequisite graph, both directions, which is what "central"
// reduces to without a centrality procedure. Q74 answers the betweenness
// reading of the same word.
MATCH (c:Course)
OPTIONAL MATCH (c)-[out:REQUIRES]->(:Course)
OPTIONAL MATCH (:Course)-[in_:REQUIRES]->(c)
RETURN c.url, c.name, count(DISTINCT out) + count(DISTINCT in_) AS degree
ORDER BY degree DESC LIMIT 20;

// Q100. Where are the structural holes — occupations reachable by only one route?
// A structural hole is where removing one edge disconnects something. Reported
// nationally over the crosswalk, which is the population the question names.
// `99-9999` is the crosswalk's NO MATCH sentinel — every programme that failed
// to map points at it, so it is the most single-routed thing in the graph and
// the least meaningful. `routes` was returned as a column and is 1 on every
// row by construction, which is a filter reported as a finding.
MATCH (p:Programme)-[:PREPARES_FOR]->(o:Occupation)
WHERE o.soc_code <> "99-9999"
WITH o, count(DISTINCT p) AS routes
WHERE routes = 1
RETURN o.soc_code, o.name
ORDER BY o.soc_code LIMIT 25;

// Q101. How does the graph's shape differ between CTE and academic subjects?
// CTE is a PATHWAY kind, not a course property — the catalogue publishes it as
// a pathway that includes courses, which is why this joins through Pathway
// rather than filtering a flag that does not exist.
// COUNTS COURSES, not rows. `count(*)` over this pattern counts
// (pathway, course, prerequisite) triples: a course with three prerequisites
// counted three times, and one included in two pathways of the same kind
// counted twice again. The column said `chained_courses` and reported neither.
MATCH (pw:Pathway)-[:INCLUDES]->(c:Course)-[:REQUIRES]->(:Course)
RETURN pw.kind, count(DISTINCT c) AS chained_courses
ORDER BY chained_courses DESC;

// Q102. If we added one course to this district, which would increase reachability most?
// THIS IS Q76'S QUERY, and saying so is the point. A counterfactual is not
// measurable against a graph that does not contain the counterfactual, so the
// closest thing is where the graph is thinnest — the entry points with the
// most dependants, which is exactly what Q76 ranks. Same rows, read for a
// different purpose: Q76 asks which entry course opens the most, and this asks
// where a new one would attach to reach the most.
//
// A ✅ resting on a query that already answers another question is worth
// flagging rather than hiding. It is kept because the ranking genuinely is the
// answer to both readings, not because two questions were merged to save work.
MATCH (d:Course)-[:REQUIRES*]->(entry:Course)
WHERE NOT EXISTS { MATCH (entry)-[:REQUIRES]->(:Course) }
RETURN entry.url, entry.name, count(DISTINCT d) AS would_extend
ORDER BY would_extend DESC LIMIT 10;
