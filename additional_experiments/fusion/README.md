# R1.5 ablations — minimal GNN (DEE and CP)

Reviewer 1 comment 5 asks for five sub-ablations. Two were already answerable
from existing runs; the remaining three — (ii) node features vs knowledge graph,
(iii) literature semantics vs article counts, (iv) concatenation vs learned
fusion — are not, because they need the model rebuilt rather than the results
rearranged.

Rather than modify SPEOS, whose architecture sits on the path of every result
already produced, these use a deliberately small GCN in which exactly one thing
varies at a time. **This is not KI-GNN**: no FiLM, no multi-relational edges, no
nested CV. The comparison is internal, between rows, which is what R1.5 asks.

Run on **DEE** (central disease) and **CP** (the disease where the published
message-passing effect goes the other way — the sharpest available check that
this model is behaving like KI-GNN and not inventing its own pattern).

## Reproducing

```bash
python additional_experiments/fusion/build_count_features.py
python additional_experiments/text_representations/align_to_speos_symbols.py \
    --matrix additional_experiments/fusion/pubmed_count_3d_2022_09.txt

# DEE, batched only to keep each call short
python additional_experiments/fusion/run_simple_gnn.py \
    --preset 1_ll_kg,2_hl_kg,3_ll+hl_kg_concat \
    -o additional_experiments/fusion/metrics_a.tsv \
    --ranks-out additional_experiments/fusion/ranks_a.tsv
# ... likewise presets 4-6 (metrics_b) and 7-9 (metrics_c)

# CP, all nine at once
python additional_experiments/fusion/run_simple_gnn.py --disease cp --preset all \
    -o additional_experiments/fusion/metrics_cp.tsv \
    --ranks-out additional_experiments/fusion/ranks_cp.tsv

python additional_experiments/fusion/contrast_simple_gnn.py --disease dee
python additional_experiments/fusion/contrast_simple_gnn.py --disease cp
```

`--disease` is not optional in spirit: configuration names repeat across
diseases, so the contrast script filters on the `disease` column and writes
per-disease outputs. Without that, globbing the rank files would silently
compare DEE rows against CP rows.

## The tables

Median rank of post-cutoff target genes, lower is better.

| # | configuration | DEE | 95% CI | CP | 95% CI |
|---|---|---|---|---|---|
| 1 | LL only (≈GNN) | 2768.5 | [2131.5, 3510] | 4374 | [3865, 5017] |
| 2 | HL only (≈C-GNN) | 2564.0 | [2034.5, 3015.5] | 1600 | [1333, 2219] |
| 3 | LL+HL concat (≈KI-GNN) | **1681.0** | [1346.5, 2126] | **1279** | [1035, 1750] |
| 4 | LL+HL sum | 1724.0 | [1250, 2089.5] | 1533 | [1303, 2036] |
| 5 | LL+HL gated | 1581.5 | [1390, 2230.5] | 1563 | [1274, 1915] |
| 6 | LL+HL, no message passing | 1829.0 | [1354.5, 2487] | 1802 | [1437, 2533] |
| 7 | Random features + KG | 6622.5 | [5612.5, 8103] | 8202 | [7184, 9175] |
| 8 | LL + article counts | 2694.0 | [1897.5, 3257] | 4106 | [3369, 4753] |
| 9 | Article counts only | 4703.5 | [4188, 5215] | 5004 | [4274, 5653] |

Rows 1–3 are the anchors, and both diseases reproduce the published ordering:

| | published GNN / C-GNN / KI-GNN | ours |
|---|---|---|
| DEE | 3002 / 2141 / 1328.5 | 2768.5 / 2564.0 / 1681.0 |
| CP | 3338 / 1309 / 1040 | 4374 / 1600 / 1279 |

## Paired contrasts

Every row ranks the same target genes, so comparing marginal CIs is the wrong
test — shared target difficulty inflates both intervals at once. These resample
genes and bootstrap the *difference*. Negative favours A.

| contrast | DEE | CP | answers |
|---|---|---|---|
| knowledge inclusion helps (3 vs 1) | **−1088** [−1823, −400] | **−3095** [−3629, −2459] | anchor |
| literature beats expression (2 vs 1) | −204 [−1021, +570] ns | **−2774** [−3360, −2021] | anchor |
| combined beats literature alone (3 vs 2) | **−883** [−1379, −395] | −321 [−885, +168] ns | anchor |
| sum vs concatenation (4 vs 3) | +43 [−305, +322] ns | +254 [−181, +650] ns | R1.5 iv |
| gated vs concatenation (5 vs 3) | −100 [−318, +390] ns | +284 [−155, +559] ns | R1.5 iv |
| message passing removed (6 vs 3) | +148 [−149, +542] ns | **+523** [+16, +908] | R1.5 v |
| graph only (7 vs 3) | **+4942** [+3765, +6569] | **+6923** [+5742, +7993] | R1.5 ii |
| graph only vs features only (7 vs 6) | **+4794** [+3395, +6469] | **+6400** [+5241, +7512] | R1.5 ii |
| counts instead of semantics (8 vs 3) | **+1013** [+59, +1702] | **+2827** [+2058, +3484] | R1.5 iii |
| counts alone vs semantics alone (9 vs 2) | **+2140** [+1362, +2921] | **+3404** [+2423, +4147] | R1.5 iii |

## What this says

**R1.5 iii — literature semantics are not a popularity proxy.** The
load-bearing result, and significant on both diseases in both forms. Replacing
MiniLM embeddings with a 3-dimensional article count is worse in combination
(DEE +1013, CP +2827) and alone (DEE +2140, CP +3404). Whatever the embeddings
contribute is not reducible to how much a gene has been written about — which
is the specific concern behind the comment.

**R1.5 ii — node features carry nearly all the signal.** The graph with
uninformative node features is far worse than features with no graph at all,
on both diseases (+4794, +6400). The KG is not a substitute for node features.

**R1.5 iv — concatenation is not the limiting choice.** Neither additive sum
nor a learned gate differs significantly from plain concatenation, on either
disease, in either direction. The benefit comes from *having* both feature
sets, not from how they are combined. Concatenation is naive, and here it costs
nothing.

**R1.5 v — message passing helps CP, not DEE, exactly as published.** This is
the result worth leading with:

| | this minimal GCN | SPEOS / KI-GNN |
|---|---|---|
| DEE | +148, ns | +115.5, ns |
| CP | **+523, significant** | **+635, significant** |

A disease-specific effect, reproduced in sign, rough magnitude *and*
significance, by an independent implementation sharing no code with SPEOS. That
is much stronger evidence than either result alone, and it directly answers the
reviewer's suspicion that the graph component might be doing nothing: it does
something, but only on some diseases, and we can now say which.

**The heterogeneity predictor holds again.** On CP, literature alone beats
expression alone decisively (−2774); on DEE the two are indistinguishable
(−204, ns). CP is also where knowledge inclusion pays off most (−3095 vs
−1088). Same pattern previously seen across 7 diseases and 4 model classes,
now in a fifth independent implementation.

One honest caveat, visible in the anchors: the two diseases split on *which*
comparison is significant. DEE gains significantly from adding literature to
expression (3 vs 2, −883) but CP does not (−321, ns), because on CP the
literature features were already carrying almost everything. Both diseases
agree on the headline (3 vs 1 significant); they disagree on where the gain
comes from, and that is a finding rather than noise.

## Why early stopping is load-bearing

The first version of this script trained for a fixed 200 epochs and produced an
ordering that *contradicted* the paper. `diagnose_simple_gnn.py` shows why: the
384-dimensional PubMed embeddings let the model drive training loss to ~1e-4,
memorising all 736 positives, after which ranking degrades monotonically.
Expression features cannot memorise (loss plateaus at 0.36), so a fixed budget
was really measuring *which feature set overfits more slowly* — the embeddings
lost simply because they fit faster.

SPEOS gets epoch selection from its inner CV folds. Rows above use the minimal
equivalent: a fifth of the positives is withheld per outer fold and the stopping
epoch is chosen on their ranking against the held-out unlabelled fold. No
post-cutoff target label is ever consulted. Selected epochs (42–170) sit well
below the 300 cap, and the feature sets that overfit fastest stop earliest,
which is the mechanism working as intended.

Worth stating in the response: a reviewer asking "did you tune the baselines as
hard as your own method?" has a real point here, and the answer is that epoch
selection is done identically and automatically for every row.
