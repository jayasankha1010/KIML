# R1.3 — does knowledge inclusion help regardless of model class?

Reviewer 1 comment 3 argues the framework is "highly selective towards RF and
one GNN implementation", and names methods that should also work: regularized
linear models, boosting such as XGBoost, MLPs, encoders, **label propagation**,
KG embeddings, heterogeneous GNNs.

The reviewer explicitly is not asking for a benchmark. The question is narrow:
is the reported benefit a property of the knowledge features, or an artefact of
the two model classes chosen? So nothing here is tuned — tuning would invite
exactly the benchmark comparison the reviewer said was unnecessary.

## Coverage

Five model classes × 7 diseases × 3 feature sets.

| model class | script | covers |
|---|---|---|
| Logistic regression | `run_model_classes.py` | "regularized linear models" |
| Random forest | `run_model_classes.py` | paper's own arm |
| Gradient boosting | `run_model_classes.py` | stands in for XGBoost |
| MLP | `run_model_classes.py` | "MLPs" |
| **Label propagation** | `run_label_propagation.py` | **"label propagation"** |

Of the three methods the reviewer named specifically, MLP and label propagation
are present directly. XGBoost is covered by `HistGradientBoostingClassifier` —
the same algorithm family; `run_model_classes.py` uses the real XGBoost
automatically when the package is installed.

## Headline

**Knowledge inclusion improves median rank in 25 of 35 disease-model
combinations.** The effect is not confined to RF and the FiLM GNN.

**The heterogeneity predictor holds in 29 of 35**: whether literature features
alone beat expression features alone predicts whether *adding* them helps. At
the disease level it was 7/7 across the first four classes.

## Label propagation specifically

Run: `python additional_experiments/model_classes/run_label_propagation.py --diseases all`
(a few seconds — the affinity graph is built once and reused across diseases).

### Why the graph is built from features

Label propagation is a graph method, but R1.3 is not asking "does a graph method
work". It asks whether the benefit survives a change of model class. Propagating
over the fixed KIML knowledge graph would not involve the feature sets at all,
so it could not answer that — and that configuration already exists as row 7 of
the fusion ablation table. Instead the affinity graph is a cosine kNN graph
(k=15) built separately from LL, from HL, and from LL+HL, so the feature sets
enter exactly as they do for every other model class.

Columns are standardised before rows are L2-normalised. Without that, LL
(cortical expression) and HL (384-dim embeddings) sit on different scales and
the larger-scale block would dominate the cosine, making the LL+HL row
effectively a single-block result.

### Positive-unlabelled handling differs, deliberately

The other four classes need out-of-fold scoring because they must invent
negatives. Label propagation does not: only positives are seeded, every other
gene starts at zero and gains score purely by proximity. No gene is ever used as
a negative, so the ranking is honest without folds. `n_folds` is recorded as 0
to make this visible rather than silently incomparable.

### Results

| disease | LL | HL | LL+HL | KI vs LL (paired) | sig |
|---|---|---|---|---|---|
| arthrogryposis | 5472.5 | 2484.5 | 2678 | −2794 [−5346, +2526] | no |
| cp | 4039 | 2077 | **1621** | **−2418 [−2973, −1758]** | **yes** |
| dee | 2539 | 3500 | **2141.5** | −398 [−1220, +260] | no |
| intellectual_disability | **2859** | 4549 | 3172 | +313 [−558, +787] | no |
| microcephaly | 3373 | 3513 | **2792.5** | −580 [−2547, +924] | no |
| mnd | 6014 | 926 | 1503 | −4511 [−10017, +2582] | no |
| platelet_disorder | 3423 | 198 | **96** | −3327 [−5887, +24] | no |

Contrasts are paired — every feature set ranks the same target genes for a given
disease, so comparing the marginal intervals would be the wrong test.

### Reading this honestly

Direction favours knowledge inclusion in **6 of 7** diseases, but only **CP
reaches significance**. That is a power limitation, not a contradiction: five of
the seven diseases have fewer than 50 post-cutoff targets (MND has 7, platelet
15, arthrogryposis 22), and the intervals are correspondingly wide. Platelet
disorder is on the boundary at [−5887, +24].

Two things are worth saying out loud rather than leaving for a reviewer to find:

1. **Intellectual disability is the one disease that regresses**, as it does in
   the paper. Here the mechanism is visible and significant: literature features
   *alone* are significantly **worse** than expression alone on ID
   (HL vs LL = **+1690 [+541, +2796], significant**). The regression is not a
   quirk of the GNN — it is a property of the ID literature.
2. **The predictor is weaker under label propagation than under the other four
   classes** (5/7 at disease level here, vs 7/7 there). DEE and microcephaly
   break it: literature alone is worse than expression alone, yet combining
   still helps. Worth stating as a limit on how far the predictor claim is
   pushed.
