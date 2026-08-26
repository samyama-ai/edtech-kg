# The CIP-SOC crosswalk — measured

The join this graph rests on. Every answerable question in
[`../questions.md`](../questions.md) traverses it: a degree programme on one
side, the occupations it leads to on the other.

Published jointly by **NCES** and the **Bureau of Labor Statistics**. Because it
is a spreadsheet rather than an API it needed its own probe, and its figures
were the last hand-counted numbers in this repo.

Every figure below is printed by `python -m etl.probe_cipsoc`. Re-run it to
verify them.

**Measured 2026-08-18T08:14:07+00:00** from
[`CIP2020_SOC2018_Crosswalk.xlsx`](https://nces.ed.gov/ipeds/cipcode/Files/CIP2020_SOC2018_Crosswalk.xlsx) — 428,901 bytes.

| | Count |
|---|---:|
| Rows on the CIP-SOC sheet | **6,097** |
| — of those, `99-9999 NO MATCH` rows | **194** |
| **Programme-to-occupation mappings** | **5,903** |
| Rows carrying a code on only one side | **0** |
| Distinct CIP codes (programmes) | **2,143** |
| — of those, mapping to an occupation | **1,949** |
| **Distinct SOC codes (occupations)** | **867** |
| CIP codes mapping to no occupation | **194** |
| SOC codes reachable from no programme | **180** |

**Two of these were wrong until edtech-kg#70, and both by the same cause.**
`99-9999` is the crosswalk's own sentinel meaning *this programme maps to
nothing*, written into the SOC column beside the words NO MATCH. It is not an
occupation, so counting it gave 868 where the answer is 867; and its rows are
not mappings, so counting them gave 6,097 where the answer is 5,903.

The 194 sentinel rows are the same 194 programmes the workbook already lists on
its "Unmatched CIP Codes" sheet — one fact stated twice, in two columns, in
agreement with itself. That is why the inflation was invisible: the table was
internally consistent and only ever one out on the occupation count.

The earlier figures reproduced the hand count taken on 2026-08-13 exactly, which
was the point of the exercise — but reproducing a hand count reproduces its
assumptions too. The probe reports both halves now, so neither figure can be
read without the other.

## What the unmatched counts mean

**194 programmes map to no occupation**, and
**180 occupations are reachable from no programme.** Both are
published by NCES in their own sheets, and both are honest limits on what this
graph can answer.

A student asking "where does this programme lead?" about one of those 194
gets nothing — not because the graph is broken, but because the crosswalk makes
no claim. That has to read as *no published mapping*, never as *no career*.

## What it is, and is not

NCES and BLS describe the crosswalk as **expert judgment about what a programme
prepares a student for**. It is not measured employment: nobody followed these
graduates and recorded where they went.

So an answer built on it says "this programme is intended to prepare you for
these occupations", not "graduates of this programme work in these occupations".
The distinction is the difference between a defensible claim and one that would
not survive scrutiny, and it belongs in every answer the product gives.

## Reproducing

```bash
python -m etl.probe_cipsoc --download   # fetch the workbook into data/
python -m etl.probe_cipsoc              # the table above
python -m etl.probe_cipsoc --json       # machine-readable, with the timestamp
```

The workbook is **not committed** — `data/` is gitignored, per the KG-repo
convention. The download refuses anything that is not a workbook, so NCES moving
the file produces a clear error rather than an HTML page parsed later as data.

Sheets present in the file: `Added Matches`, `CIP-SOC`, `File Guide`, `New CIP`, `New SOC`, `SOC-CIP`, `Unmatched CIP Codes`, `Unmatched SOC Codes`.

## Licence

Published by NCES and BLS, both US federal agencies — **US-government public
domain**. Landing page: <https://nces.ed.gov/ipeds/cipcode/post3.aspx?y=56>

Unlike the Urban Institute API, there is no third-party wrapper here, so no
second set of terms to check. This is the publisher's own file.
