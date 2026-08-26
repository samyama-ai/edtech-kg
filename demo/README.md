# Demo

A narrated walk through one district's course catalogue, as a graph. Twenty-one
questions in five tiers, climbing from ones a spreadsheet answers perfectly to
ones nothing published can answer at all. Every figure is read from the engine
as it runs — nothing is stored in the script, so a number that has changed shows
as a changed number rather than as stale text.

```bash
docker run -d --rm -p 8200:8080 public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
python -m etl.load_pwcs --url http://localhost:8200 --graph edtech

SAMYAMA_URL=http://localhost:8200 python -m demo.demo
SAMYAMA_URL=http://localhost:8200 python -m demo.demo --only 0,5,8,11,13,15,17,19
python -m demo.demo --list      # the questions, no engine needed
```

Pacing belongs to the presenter: it waits for Enter between questions unless
`--auto` is passed.

The `--only` set above is the eight that fit a short meeting: one per tier, plus
the two that tend to start a conversation — fail Algebra 1 and 28 courses close
off, and they are not the subjects anyone expects.

## The GIF at the top of the repo README

Seven questions, tier 1 to tier 4, in about twenty seconds. Both the `.cast` and
the `.gif` are committed, so it can be re-rendered when the figures change
rather than being a screenshot nobody can reproduce.

```bash
SAMYAMA_URL=http://localhost:8200 asciinema rec --cols 132 --rows 30 --overwrite \
  -c "python -m demo.demo --only 0,5,11,13,15,16,17 --auto --rows 8" \
  demo/edtech-kg.cast

agg --font-size 14 --theme monokai demo/edtech-kg.cast demo/edtech-kg.gif
```

Three choices in that command are deliberate, and each was arrived at by looking
at the result:

**132 columns, not 80.** The narration lines run to 131 characters. A narrower
terminal breaks them mid-word, which reads as sloppy in the one artefact most
people will judge this repo by.

**`--rows 8`.** Keeps every table inside one screen, so no answer is half-shown
when the next question arrives.

**Q17 closes it, not Q19.** Q19 is the more interesting question — what a
pathway requires that its own page never says — but the CTE pathway names are
long enough to wrap that table into an unreadable block. Q17 ends on
`Algebra 1 — 28`, which is the number the whole demo builds toward.
