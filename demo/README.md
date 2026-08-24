# Demo

Narrated walkthrough of the Education-to-Career Pathways KG, run live against the graph.

Twenty-one questions in five tiers, climbing from ones a spreadsheet answers perfectly to
ones nothing published can answer at all. Every figure is read from the engine as the demo
runs — nothing is stored in the script, so a number that has changed shows as a changed
number rather than as stale text.

```bash
docker run -d --rm -p 8200:8080 public.ecr.aws/f9f6l5u4/samyama-graph:1.1.0
python -m etl.load_pwcs --url http://localhost:8200 --graph edtech

SAMYAMA_URL=http://localhost:8200 python -m demo.demo
SAMYAMA_URL=http://localhost:8200 python -m demo.demo --only 0,5,8,11,13,15,17,19
python -m demo.demo --list      # the questions, no engine needed
```

The `--only` set is the eight that fit a short meeting: one tier each, plus the two that
tend to start a conversation — fail Algebra 1 and 28 courses close off across 14 subjects,
and 395 of 791 courses sit on no chain at all.

## Recording it

```bash
asciinema rec --overwrite -c "bash -c 'python -m demo.demo'" demo/edtech-kg.cast
agg demo/edtech-kg.cast demo/edtech-kg.gif
```

Tiers 4 and 5 are answered by nothing published, by anyone — that is the point of
including them, and the recording should not cut before them.
