# XGDAG as an external comparator (R1.8 / R3.2)

Both reviewers name XGDAG specifically. This is the plan for running it on our
diseases, with the requirements established by reading the code rather than the
papers.

> Mastropietro A, De Carlo G, Anagnostopoulos A. **XGDAG: explainable
> gene–disease associations via graph neural networks.** *Bioinformatics*
> 39(8):btad482, 2023. <https://github.com/GiDeCarlo/XGDAG>

## What XGDAG actually needs

`CreateGraph.py` does **not** compute node features — it reads them:

```python
nedbit_features = pd.read_csv(PATH_TO_DATASETS + disease_id + '_features')
```

So three inputs are required per disease:

| input | format | where it comes from |
|---|---|---|
| PPI network | `gene1 gene2`, official symbols | BioGRID, shipped with NIAPU |
| seed genes | `gene score` per line | **ours** — the 2022-09 panel |
| NeDBIT features | CSV `name,class,degree,ring,NetRank,NetShort,HeatDiff,InfoDiff` | computed by **NIAPU** |

The repo ships 10 precomputed DisGeNET diseases (C0001973 alcoholism,
C0011581 depression, C0023893 liver cirrhosis, C0376358 prostate cancer …).
**None overlaps our panels**, so the shipped features are of no direct use and
we must generate our own.

The features come from the same authors' companion tool:

> Stolfi P, Mastropietro A, et al. **NIAPU: network-informed adaptive
> positive-unlabeled learning for disease gene identification.**
> *Bioinformatics* 39(2):btac848, 2023. <https://github.com/AndMastro/NIAPU>

Good news: that step is Perl + C, not PyTorch. Only the GNN/explainer stage
needs the heavy environment.

## Feasibility — checked, not assumed

Gene-symbol overlap against NIAPU's BioGRID file (19,761 genes):

| list | in BioGRID |
|---|---|
| DEE seeds (2022-09) | 793 / 825 (96%) |
| DEE targets (post-split) | 203 / 223 (91%) |
| CP seeds | 91 / 92 (99%) |

The misses are ordinary HGNC renames — `AARS1`←`AARS`, `ATP5F1A`←`ATP5A1`,
`ADGRL1`←`LPHN1` — because BioGRID 4.4.206 predates them. The alias mapping in
`text_representations/align_to_speos_symbols.py` recovers most of these, and
should be applied before generating seed files.

For scale: 203 rankable DEE targets is comparable to ToppGene's 192, so the
comparison will have similar power.

## Step 1 — NeDBIT features (no GPU, no PyG)

```bash
git clone https://github.com/AndMastro/NIAPU.git
cd NIAPU/src
gcc -O2 -o nedbit_calc nedbit_features_calculator.c -lm

# seed file: "gene score", one per line
awk 'NF{print $1" 1.0"}' \
  ../../KIML/data/kiml_data/diseases/DEE-2022_09.txt > dee_seeds.txt

perl preprocess.pl ../data/biogrid_gene_pairs_clean_Hs_4_4_206.txt \
     dee_seeds.txt out_links out_genes
./nedbit_calc out_links out_genes dee_nedbit_features
```

**Decision: what score to give each seed.** XGDAG's shipped files carry
DisGeNET association scores (`NAT1 0.31`). PanelApp green genes have no
equivalent continuous confidence, so uniform `1.0` is the honest choice — but
it is a deviation and must be stated, because NeDBIT explicitly weights seeds
unequally. If challenged, the fallback is to weight by PanelApp evidence level.

## Step 2 — XGDAG graph, training, ranking

```bash
git clone https://github.com/GiDeCarlo/XGDAG.git
# place dee_nedbit_features as Datasets/DEE_features
# place dee_seeds.txt      as Datasets/DEE_seed_genes.txt
python CreateGraph.py          # builds the graph, largest connected component
python TrainerScript.py        # GraphSAGE + PU learning
python ComputeRankingScript.py # explainability-based ranking -> Rankings/
```

Needs **PyTorch 1.12 + PyG 2.1** (`CondaEnvs/` in the repo). That is a separate
environment again — neither `speos_kiml` nor `mantis-env` will do.

## Step 3 — score it like every other comparator

The ranking lands in `Rankings/`. Convert to the schema `revision_analysis.py`
already reads, then score with the same protocol as ToppGene:

- paired contrasts on the **common** target set, never raw medians across
  different universes;
- report how many targets XGDAG **cannot rank** (absent from the BioGRID
  largest connected component), as we do for ToppGene's 30 of 223 — scoring a
  method only on the genes it happens to cover rewards the omission.

## How to frame it

XGDAG belongs to **argument 2** — how do existing published methods do — along
with ToppGene, SPEOS-as-published and Mantis-as-published. It is **not** an
ablation arm.

Worth stating plainly: XGDAG uses network topology only. It has no expression
and no literature features. That is not a criticism, it is what the method is,
and it makes the comparison informative in a specific way — if KIML wins, the
question becomes how much of the gain is simply having more information types,
which is exactly what the R1.5 ablations answer.

## Risks, in order

1. **The seed-score deviation** (above). Documented, defensible, but a real
   departure from how the method was published.
2. **PyG 2.1 / torch 1.12** is old. If the environment will not build on
   Spartan, the GNN stage stalls and only the NeDBIT features are reusable.
3. **Universe mismatch.** BioGRID's largest connected component is not our
   17,282-gene universe. Handle exactly as for ToppGene — common target set and
   paired tests.
4. **Reproduce one of their diseases first.** Before trusting our adaptation,
   run a shipped disease (e.g. C0011581) end to end and check the ranking
   against `Rankings/`. If their own result does not reproduce, nothing built
   on top of it means anything.

Risk 4 is the gate. Everything else is tractable.
