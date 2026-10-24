# Supp_Data_2 — the "Fold Enrichment 1%" block reports FE@5% for RF

## The error

In `rebuttal/Supp_Data_2.xlsx`, sheet **Summary**, the block headed
*Fold Enrichment 1%* takes its **RF** values from the wrong source column.

- The **GNN** columns are correct: they match `fold_enrichment_top_1_pct` in
  the `speos_rank_metrics` sheet.
- The **RF** columns do not. Every one of them matches
  `fold_enrichment_top_5_pct` in the `Mantis_rank_metrics` sheet instead.

Verified exhaustively: **0 of 54 RF cells correct, all 54 match FE@5%.**
(27 unique disease × arm cells; the Summary sheet repeats the block twice.)

So the table as published compares **RF at the 5% threshold against GNN at the
1% threshold**. The two halves of each row are not on the same footing, and
because FE@1% is almost always the larger number, the error systematically
understates RF.

The other three blocks in the same sheet are fine:

| block | RF cells correct | wrong |
|---|---|---|
| median rank | 53 | 1 (rounding, below) |
| **FE@1%** | **0** | **54** |
| precision@100 | 27 | 0 |
| recall@100 | 27 | 0 |

## Scope — manuscript text and tables are NOT affected

Checked directly:

- **Table 1 is median rank, not fold enrichment.** All its values match the
  source sheets.
- No fold-enrichment table appears in `Supplemantary_figures_tables.pdf`. The
  only "fold enrichment" mentions there are figure captions for the GO/HPO
  enrichment analyses, which are a different quantity entirely.

The error is therefore confined to one block of one sheet in one supplementary
data file. It still needs correcting, because that file is the published record
of the metric.

One unrelated nit: Arthrogryposis RF HL median rank is `3732` in both the
Summary sheet and Table 1, against `3732.5` in the source. Rounding, not an
error of substance.

## Corrected values

Full table in `fe1_correction.tsv` (`rf_published_fe1`, `rf_corrected_fe1`,
`gnn_fe1` per disease × arm). The KI (LL+HL) column, which is the one the
paper's claims rest on:

| disease | RF published | RF corrected | GNN | winner |
|---|---|---|---|---|
| DEE | 7.5 | **10.4167** | 7.8125 | GNN → **RF** |
| AD DEE | 12.0548 | **20.5479** | 20.3125 | GNN → **RF** |
| AR DEE | 6.6667 | 4.1667 | 10.8696 | GNN (unchanged) |
| Microcephaly | 2.9167 | 4.1667 | 0 | RF (unchanged) |
| Intellectual Disability | 3.786 | 3.7037 | 1.81 | RF (unchanged) |
| Motor Neuron Disease | 14.2857 | **28.5714** | 28.5714 | GNN → **tie** |
| Cerebral Palsy | 7.7778 | 13.6752 | 14.5923 | GNN (unchanged) |
| Bleeding and Platelet Disorder | 16.25 | 50 | 53.3333 | GNN (unchanged) |
| Arthrogryposis | 5 | 16.6667 | 22.7273 | GNN (unchanged) |

## Why this matters

Correcting it **changes which arm wins on 3 of 9 diseases, including DEE** —
the paper's central disease. On DEE the corrected KI-RF fold enrichment
(10.4167) is higher than KI-GNN (7.8125), where the published table showed the
reverse (7.5 vs 7.8125).

This does not touch the paper's main claim, which is that adding expert-curated
knowledge improves prioritisation within each model family — that claim rests on
median rank, is unaffected, and still holds. What changes is the secondary
RF-versus-GNN comparison on this one metric. Anywhere the text leans on GNN
outperforming RF by fold enrichment, the support is not there.

Better to fix and state this ourselves than have a reviewer recompute it. The
reviewers already asked for additional metrics (R1.10), so this block will be
looked at.

## Reproducing

```bash
python additional_experiments/supp_fixes/check_supp_data_2.py
```
