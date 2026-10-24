# Existing prioritisers: ToppGene and the benchmark table (R1.8 / R3.2)

This directory serves the **second** of the rebuttal's two arguments.

1. *Does knowledge improve gene prioritisation?* — the ablation family, the same
   architecture trained on experimental data, on knowledge, and on both. That
   argument lives in `fusion/` and `model_classes/`.
2. *How well do existing published methods do, and where does KIML sit among
   them?* — this directory.

SPEOS and Mantis appear in both. Here they are the **published methods in their
own right**: SPEOS = GNN and Mantis = RF, each using the experimental data they
were published with. ToppGene is an existing method and nothing more — it is
not an ablation arm and should not be read as one.

The knowledge-only arms (C-GNN, C-RF) belong to argument 1 and are **excluded
from the benchmark table**. They stay in `toppgene_vs_kiml_contrasts.tsv`
because they are useful for diagnosing the intellectual-disability result, not
as comparators.

```bash
python additional_experiments/other_prioritizers/run_toppgene_metrics.py
python additional_experiments/other_prioritizers/benchmark_table.py          # argument 2
python additional_experiments/other_prioritizers/contrast_toppgene_vs_kiml.py # diagnostics
```

## Benchmark table

Median rank on a **common target set** per disease — every method in the row
must be able to rank the gene, so columns are directly comparable. Lower is
better.

| disease | targets | ToppGene | SPEOS | Mantis | KI-GNN | KI-RF |
|---|---|---|---|---|---|---|
| dee | 191 | 2111 | 2934 | 1961 | 1392 | **1201** |
| cp | 226 | 1493 | 3338 | 1918 | **1036** | 1463 |
| ad_dee | 63 | 2444 | 1294 | **719** | 1114 | 756 |
| ar_dee | 46 | 3005 | 4771 | 1777 | 1718 | **1624** |
| arthrogryposis | 22 | **2103** | 6948 | 3436 | 2198 | 2471 |
| microcephaly | 41 | 4220 | 4673 | 3378 | 3701 | **2672** |
| mnd | 7 | 738 | 3936 | 5305 | **407** | 669 |
| intellectual_disability | 211 | 3014 | 2907 | **2130** | 3843 | 2791 |

## Against the best existing method on each disease

The honest test is not "does KIML beat ToppGene" but "does KIML beat the
strongest existing method available for that disease". Negative favours KIML.

| disease | best existing | KI-GNN | sig | KI-RF | sig |
|---|---|---|---|---|---|
| cp | ToppGene | **−448** [−991, −84] | **yes** | −32 [−728, +523] | no |
| dee | Mantis | −569 [−1212, +144] | no | **−760** [−1335, −119] | **yes** |
| ar_dee | Mantis | +24 [−777, +1964] | no | −105 [−783, +780] | no |
| arthrogryposis | ToppGene | −51 [−2276, +2075] | no | +440 [−1416, +1483] | no |
| mnd | ToppGene | −331 [−10228, +4950] | no | −69 [−7034, +540] | no |
| microcephaly | Mantis | +323 [−1359, +1759] | no | −706 [−2162, +765] | no |
| ad_dee | Mantis | +395 [−67, +1223] | no | +37 [−171, +225] | no |
| intellectual_disability | Mantis | **+1713** [+817, +2341] | **loses** | +661 [−51, +1241] | no |

**KIML significantly beats the best existing method on 2 of 8 diseases** (CP
via KI-GNN, DEE via KI-RF), **significantly loses on 1** (ID via KI-GNN), and
ties on the other 5.

### This is weaker than comparing against ToppGene alone — deliberately

Measured against **ToppGene only**, KI-GNN wins significantly on DEE, CP and
AD DEE and never loses. That is a true statement and it is in
`toppgene_vs_kiml_contrasts.tsv`. But on several diseases the strongest
existing method is **Mantis**, not ToppGene, and Mantis is a hard baseline.
Quoting only the ToppGene comparison would overstate the result, so the table
above uses the best existing method per disease.

Note the consequence of SPEOS and Mantis doing double duty: "KI-RF beats
Mantis" is simultaneously an argument-2 benchmark result and an argument-1
ablation result, because Mantis *is* the RF arm. On DEE that comparison is
significant (−760); elsewhere it is not.

### Intellectual disability is a genuine loss

KI-GNN is significantly **worse** than Mantis on ID (+1713 [+817, +2341]).
The mechanism is the one found everywhere else in this revision: on ID the
knowledge-only arms collapse (C-GNN −2968, C-RF −2208 against ToppGene, both
significant) while the experimental-data arms are fine. ID's literature is the
problem. This is consistent with the label-propagation result, where HL-only
was significantly worse than LL-only on ID, and with the published ID
regression — but it should be stated as a limitation, not explained away.

## Caveats, reported rather than smoothed over

**1. ToppGene defines its own universe.** Its output already excludes the seed
genes, so no re-ranking is needed, but the candidate list is ToppGene's.

**2. Universes differ in size** (~14.9k for ToppGene against ~16.5k unlabelled
for KIML). Raw median rank rewards whichever method ranks over fewer genes,
which *favours ToppGene*. Two mitigations: the benchmark table scores every
method on a common target set and all significance tests are paired;
`benchmark_existing_methods.tsv` and `toppgene_metrics.tsv` both carry
percentile columns alongside raw ranks.

**3. Some targets are absent from ToppGene's background entirely** — 30 of 223
for DEE, only one (`B4GAT1` → `B3GNT6`) recoverable through an HGNC alias.
ToppGene cannot rank those genes at all, and scoring it only on genes it
happens to cover would quietly reward the omission. `run_toppgene_metrics.py`
therefore reports two variants: `rankable` (covered targets only, ToppGene's
best case) and `penalised` (unrankable targets pushed past the end of the
list, which is what a user actually experiences). The benchmark table uses the
common rankable set, since a rank difference is undefined otherwise.

For DEE the rankable target set is **exactly the same 192 genes** our GNN runs
scored, so nothing is lost to intersection there.

## Mapping files to diseases is verified, not assumed

Because ToppGene excludes the genes it was seeded with, the correct pairing is
the one where almost none of the 2022-09 panel appears in the ranked output.
`run_toppgene_metrics.py` checks this and skips any pairing that fails rather
than silently scoring a mismatched file. All 11 mappings pass.

`ToppGeneData_ataxia_random.csv` is deliberately unmapped: the name indicates a
randomised-seed control rather than a disease panel, and guessing a pairing for
it would invent a result.

## Data handling

The raw ToppGene web exports are ~50 MB across 12 files, with 21 columns of
which two are used. They were produced by hand and are **not**
script-regenerable, so `Rank` and `GeneSymbol` are extracted to
`toppgene_rankings.tsv` (3.8 MB, verified to reconstruct the rankings exactly)
and that file is tracked; the raw exports are gitignored. **Keep the raw
exports backed up outside git.**

## Note on the earlier `toppgene/ranker.py`

That script hardcodes `summary_row["InputFile"] = "ToppGeneData_DEE_AR.csv"`
regardless of which file it processed, so all five rows in `rank_summary.csv`
carry the same label and cannot be attributed to a disease. Its DEE median
(2118) reproduces here, so the numbers were right and only the labels were
wrong. The scripts in this directory supersede it.

## Still outstanding

- **Endeavour** — service shut down; not recoverable.
- **Phenolyzer, XGDAG** — not yet attempted.
