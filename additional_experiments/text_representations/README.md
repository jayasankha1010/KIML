# R1.4 / R1.5(i) — sentence transformer vs classical text representations

Reviewer 1 comment 4 asks whether the MiniLM sentence-transformer embeddings
are doing something a classical text representation could not. Four
representations, all reduced to the same 384 dimensions, all built from the
same pre-2022-10 PubMed corpus:

| representation | what it is |
|---|---|
| MiniLM | the published arm, pretrained sentence transformer |
| TF-IDF full | TF-IDF + SVD, titles **and** abstracts |
| TF-IDF title | TF-IDF + SVD, titles only |
| Doc2Vec | learned and dense like MiniLM, but trained only on this corpus |

Two text scopes separate "what abstracts add" from "what titles already carry".
Doc2Vec separates "classical methods suffice" from the sharper "pretraining
adds nothing" — it is dense and learned, differing from MiniLM mainly in not
being pretrained on external text.

All matrices are re-keyed to the SPEOS symbol namespace by
`align_to_speos_symbols.py`, so every arm scores on an identical universe.
Without that, the classical arms would silently lose 2,029 genes and the
comparison would be rigged in MiniLM's favour — precisely the bias this
comment is testing for.

## Answer: the sentence transformer is not contributing anything

### At the GNN level — the architecture the paper's claims rest on

```bash
python additional_experiments/text_representations/run_gnn_arm_metrics.py
```

| disease | MiniLM | TF-IDF full | TF-IDF title | Doc2Vec |
|---|---|---|---|---|
| dee | 1328.5 | **1027** | 1118.5 | 1373.5 |
| cp | 1065 | 873 | 932 | **781** |

Paired against MiniLM (negative = the alternative ranks targets higher):

| disease | representation | difference [95% CI] | sig |
|---|---|---|---|
| dee | TF-IDF full | −302 [−668, +29] | no |
| dee | TF-IDF title | −210 [−559, +231] | no |
| dee | Doc2Vec | +45 [−392, +402] | no |
| cp | TF-IDF full | −192 [−429, +58] | no |
| cp | TF-IDF title | −133 [−374, +144] | no |
| cp | **Doc2Vec** | **−284 [−511, −60]** | **yes** |

**MiniLM places 3rd of 4 on DEE and 4th of 4 on CP.** An alternative beats it
in 5 of 6 paired comparisons, one of them significantly.

The baseline here is `Rev_<disease>_KIGNN_s1`, **not** the published MiniLM
number. SPEOS never calls `torch.manual_seed`, so two runs of the same
configuration differ; comparing a new TF-IDF run against the published figure
would confound the representation with run-to-run variance. Using the `Rev_`
run from the same batch makes the literature matrix the only difference.

### At the classifier level — 28 disease × model cells

Restricted to the combined (LL+HL) arm, asking which representation gives the
best median rank in each cell:

| representation | cells where it is best |
|---|---|
| TF-IDF full | **14** |
| TF-IDF title | 9 |
| Doc2Vec | 4 |
| **MiniLM** | **1** |

Head-to-head against MiniLM: TF-IDF full wins 23–5, TF-IDF title 20–8,
Doc2Vec 20–8.

### Why Doc2Vec matters — this is the decisive result

**CP Doc2Vec beats MiniLM by −284 [−511, −60], significant.** It is the only
significant result in the GNN arm, and it is the most informative one.

Doc2Vec is dense and learned exactly like MiniLM. The one thing it lacks is
pretraining on external text — it sees only our own cutoff-restricted corpus.
So a model with strictly *less* information outperforms the pretrained
transformer. The conclusion is therefore not "classical sparse methods happen
to suffice" but **pretraining contributes nothing here, and may cost
something**. The signal is in the literature content, not the encoder.

Doc2Vec is weakest on DEE (1373.5, +45 vs MiniLM, ns) and strongest on CP, so
the effect is disease-dependent rather than uniform. Both statements should be
made; quoting only CP would overstate it.

## How to frame this

This does **not** undermine the central claim. Knowledge inclusion still helps:
25 of 35 disease-model combinations in `model_classes/`, and the full ablation
table in `fusion/`. What changes is the account of *why* it helps.

The defensible reading is that KIML is **robust to the choice of text
representation** — a simpler, cheaper encoder does the same job. That is a
better result than a fragile dependency on one pretrained model, and it makes
the method easier to reproduce. But any manuscript text that presents MiniLM as
a sophisticated or necessary choice needs softening, and titles-only being
competitive (1118.5 vs 1027 on DEE) suggests abstracts add little either.

Better to state this ourselves. A reviewer who already suspects the embeddings
are doing less than claimed will test exactly this, and the data is
unambiguous in direction across two independent levels of analysis.

## Status — complete

All four representations are done at both the classifier and GNN level, on DEE
and CP.

The Doc2Vec GNN runs took three attempts, for two unrelated reasons worth
recording:

1. The first two died on a full cluster disk mid-checkpoint
   (`PytorchStreamWriter failed writing file data/0`).
2. The third trained and summarised successfully but still reported failure:
   `run_revision.slurm` extracted the disease with `[A-Za-z-]+`, which does not
   match digits, so `KIGNN-DOC2VEC` (the "2") fell through and
   `evaluate_results.py` died with `Unknown disease:
   Rev_dee_KIGNN-DOC2VEC_s1`. The probabilities files were already written, so
   nothing needed re-running — only the convenience TSV was lost. The regex now
   allows digits and the script fails fast if extraction is a no-op.

## Files

| file | contents |
|---|---|
| `build_text_features.py` | builds TF-IDF/SVD and Doc2Vec matrices, `--text-scope {full,title}` |
| `build_text_features.slurm` | cluster job for the above (gensim installed in-script) |
| `align_to_speos_symbols.py` | re-keys a matrix to the SPEOS namespace |
| `run_gnn_arm_metrics.py` | GNN-level metrics and paired contrasts |
| `gnn_arm_metrics.tsv` | per-arm metrics with CIs |
| `gnn_arm_metrics_contrasts.tsv` | paired contrasts against MiniLM |

The `*.txt` matrices are ~60 MB each and gitignored — transfer with rsync, see
`additional_experiments/README_data_transfer.md`.
