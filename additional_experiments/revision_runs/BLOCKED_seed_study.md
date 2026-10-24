# BLOCKED — 5-seed study for the R1.5b configurations

**Blocked 2026-10-22: Spartan project disk quota exhausted.** Resume when space
is available. Nothing else depends on this; it strengthens an existing result
rather than enabling a new one.

## Why it is needed

The R1.5b graph effects are statistically significant but sit at the noise
floor of retraining.

Confidence intervals everywhere in this revision resample the **target genes**
with the model held fixed (`revision_analysis.bootstrap`). They answer "if a
different set of genes had been curated after the cutoff, how much would this
move?" They do **not** cover retraining — and SPEOS never calls
`torch.manual_seed`, so model variance is uncontrolled rather than merely
unmeasured.

Configurations that happened to be run twice show how much that matters:

| disease | arm | run 1 | run 2 | shift | CI width | shift / width |
|---|---|---|---|---|---|---|
| cp | GNN | 3338 | 3971 | **+633** | 1893 | **33%** |
| intellectual_disability | KI-GNN | 3771 | 3969 | +198 | 1289 | 15% |
| dee | KI-GNN | 1379 | 1328.5 | −50.5 | 698 | 7% |
| dee | GNN | 2915 | 3002 | +87 | 1830 | 5% |

The R1.5b **graph** effects are −290 (DEE) and −240 (CP) — the same order as
that +633. So "significant" currently means *significant given these two
particular trained models*, not *significant across retraining*.

Not affected, and needing no seed study: the R1.5b **feature** effects (−1202
to −2666) and R1.5e on CP (+635). Those are an order of magnitude above
anything seen here.

## Commands

```bash
SPARTAN=culuwitikega@spartan.hpc.unimelb.edu.au
KIML=/data/gpfs/projects/punim0512/chathura_projects/KIML

# check there is room first - this is what failed last time
ssh "$SPARTAN" "df -h $KIML | tail -1; du -sh $KIML/external/SPEOS/results"

ssh "$SPARTAN" "cd $KIML && git pull && \
  python additional_experiments/revision_runs/make_configs.py \
    --diseases dee cp --variants GNN GNN-KG KIGNN-PPI KIGNN \
    --seeds 5 --append"

ssh "$SPARTAN" "cd $KIML && grep -nE \
  '^Rev_(dee|cp)_(GNN|GNN-KG|KIGNN-PPI|KIGNN)_s[2-5]\$' \
  external/SPEOS/revision_manifest.txt"
# line numbers minus 1 = array indices

sbatch --array=<first>-<last>%4 additional_experiments/revision_runs/run_revision.slurm
```

2 diseases × 4 variants × 5 seeds = 40 runs. Seed 1 already exists for all
eight combinations, so `--append` adds **32 new jobs**, ~1–1.5 h each.

## Three things that will bite

- **Use `--append`.** Without it `make_configs.py` deletes every `Rev_*.yaml`
  and rewrites the manifest from scratch, renumbering the array indices.
- **Use `%4` throttling.** Each run writes 30 fold checkpoints (6 outer × 5
  inner). Submitting 32 unthrottled is what exhausted the quota. Old
  checkpoints from already-summarised runs are safe to delete — once a run is
  summarised, only its `*_probabilities.tsv` matters.
- **The cluster needs the 2026-10-22 commit** of `run_revision.slurm`. The
  disease-extraction regex previously used `[A-Za-z-]+`, which does not match
  digits, so `KIGNN-DOC2VEC` (the "2") fell through and `evaluate_results.py`
  died with `Unknown disease: Rev_dee_KIGNN-DOC2VEC_s1` — after training and
  summarisation had already succeeded. A guard now fails fast instead.

## Afterwards

1. Pull `*_probabilities.tsv` into `paper_predictions/`.
2. `run_speos_ablation_metrics.py` hardcodes `--seed-tag s1`. It needs a
   seed-aware mode reporting **both** the across-seed spread and the
   target-resampling CI — they are different quantities and should not be
   merged into one interval.
3. Update the caveats in `rebuttal/build_reviewer_workbook.py`: the R1.5b
   paragraph on tab "R1.5b + R1.5e SPEOS", and the retraining section of the
   R1.10 tab.

Related: task #21 (add seeding to SPEOS). This study partly answers it, but the
underlying problem — that the published numbers came from a single unseeded run
that cannot be reproduced exactly — is worth fixing in the public repo
regardless.
