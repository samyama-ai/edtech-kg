# Who already sells this

Answering edtech-kg#47. Sandeep named GT.school, Ellucian and LTS Education in
the 2026-08-18 review. The goal it serves is *"a demo that helps their product
roadmap and their customers do something better, faster or cheaper"* — and you
cannot argue "better" without knowing what the current best is.

**READ THE LIMIT FIRST.** This measures **what a vendor's public page says**,
counted. It is not a capability comparison and cannot be one: a page that does
not mention degree audit is a page, not a product without one. Every figure
below is a term count over one page we were permitted to fetch, and the record
names the page.

## What was measured

| vendor | page bytes | readable chars | planning terms found |
|---|---:|---:|---|
| GT.school | 122,100 | 9,276 | **none** |
| Ellucian | 130,228 | 8,207 | `api` 1, `knowledge graph` 1 |
| LTS Education | — | — | **unreachable** |
| PowerSchool (Naviance) | 119,808 | 5,525 | `api` 1 |
| Stellic | 305,861 | 7,085 | `advisor` 8, `degree audit` 1, `pathway` 2 |
| Civitas Learning | 462,822 | 8,105 | **none** |

Both lengths are recorded on purpose. A term count of zero over **no text** is
a reader artefact; a term count of zero over 8,105 characters is a finding.
[`sources/case.md`](../standards/case.md) shipped a `bytes: 0` that turned out to
be an artefact of a discarded response body, and this is the same trap one
page over.

## What it says

**The incumbent has no reachable product page.** Naviance is the default in US
high-school course planning, and `powerschool.com/products/naviance/` and
`.../college-career-readiness/naviance/` both answer **404**, while
`naviance.com` answers 200 with **212 bytes** — a redirect stub. What is
measured above is PowerSchool's own home page, because that is what is
actually published.

**Only one of six mentions degree audit at all.** Stellic — *"student journey
and academic planning platform"* — carries `degree audit` once and `pathway`
twice. Nobody else in the set mentions either on the page they lead with.

**Ellucian says "knowledge graph".** Once, on its solutions page. The largest
vendor here uses the term we build on, which is worth knowing before anyone
claims the category is empty.

**GT.school is not a competitor.** The review suggested it would "help you
learn a few things", and measuring says it is a **school** — *"gifted
education for k-8 students in texas"* — not a planning product. That is a
useful negative: the named list contained one entry that is a different kind
of thing.

**LTS Education does not answer.** Consistent with the issue's own note that
it is no longer trading. Recorded as unreachable rather than refused, because
a company that has stopped and a company that blocks us are different facts.

## Who we did not ask, and why

**Coursicle — not fetched.** Its `robots.txt` carries `Disallow: /` for a list
of user-agents including `ClaudeBot`, `anthropic-ai` and `Claude-Web`. This
repo's agent string is none of those, so a parser says the fetch is permitted.

We did not fetch it. The publisher's intent is plainly to exclude automated
agents of this kind, and a finding resting on our user-agent not appearing on
their list would be technically permitted and worth nothing.

That is the same shape as [`graduation-requirements.md`](graduation-requirements.md),
where ECS answers `Disallow: /` and the refusal became the finding — except
here the rules do not name us and we stopped anyway.

## What this does not establish

One page per vendor, on one day. A vendor's front page is a marketing choice,
not an inventory: Naviance certainly does course planning, and its 404s say
something about its web estate rather than its product.

What the counts DO support is narrower and still useful: **on the page each of
these companies leads with, the vocabulary of prerequisite structure is almost
absent.** Five of six do not use it at all. That is a fact about how the
category is sold, and it is the gap a demo would be landing in.
