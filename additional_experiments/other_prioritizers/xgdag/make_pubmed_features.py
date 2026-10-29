"""
PubMed node features for XGDAG, in the BioGRID symbol namespace.

This supports the ablation XGDAG-vs-XGDAG+PubMed, which is a better use of
XGDAG than the head-to-head benchmark. The cross-method comparison is dogged
by confounds we cannot remove - XGDAG ranks 4,940 genes against our 16,546,
misses 47% of DEE targets, and we had to give every seed a uniform score. A
WITHIN-METHOD ablation holds all of that fixed, so any difference is
attributable to the literature features.

It also makes the knowledge-inclusion claim architecture-independent across
three unrelated GNN frameworks: SPEOS (FiLM), our minimal GCN, and XGDAG
(GraphSAGE + PU + explainability).

TWO MATRICES ARE WRITTEN, and the second is what makes the first
interpretable:

  pubmed   384 MiniLM dimensions, aligned to BioGRID symbols
  random   384 dimensions of noise, same shape, same zero-filled genes

XGDAG's six NeDBIT features become 390 with PubMed added - a 65x wider input
to SAGEConv(num_features, 16). If PubMed helps, a reviewer will reasonably ask
whether that is the literature CONTENT or simply more capacity. The random
block answers it: if noise helps too, the gain is capacity; if only PubMed
helps, it is content. Same control as R1.5(iii).

Genes in BioGRID with no embedding are zero-filled rather than dropped, so the
graph keeps its topology - dropping them would change the network itself and
make the two arms incomparable.

Usage:
    python make_pubmed_features.py --ppi /path/to/NIAPU/data/biogrid_...txt
"""

import argparse
import csv
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EMBEDDINGS = os.path.join(ROOT, "data", "kiml_data", "pubmed_embeddings",
                          "pubmed_embeddings_rearranged_2022_09.txt")
HGNC = os.path.join(ROOT, "external", "SPEOS", "hgnc", "hgnc_official_list.tsv")


def load_aliases(path):
    """symbol -> other names it is known by, in both directions."""
    both = {}
    if not os.path.exists(path):
        return both
    with open(path) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            current = (row.get("symbol") or "").strip()
            if not current:
                continue
            olds = set()
            for field in ("prev_symbol", "alias_symbol"):
                raw = (row.get(field) or "").replace('"', "")
                olds.update(s.strip() for s in raw.split("|") if s.strip())
            for old in olds:
                both.setdefault(current, set()).add(old)
                both.setdefault(old, set()).add(current)
    return both


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ppi", required=True)
    parser.add_argument("--embeddings", default=EMBEDDINGS)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out-dir", default=os.path.join(HERE, "features"))
    args = parser.parse_args()

    universe = set()
    with open(args.ppi) as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 2:
                universe.update(parts[:2])
    print("BioGRID universe: {} genes".format(len(universe)))

    vectors, width = {}, None
    with open(args.embeddings) as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2:
                continue
            vectors[parts[0]] = parts[1:]
            width = width or len(parts) - 1
    print("embeddings      : {} genes x {} dims".format(len(vectors), width))

    aliases = load_aliases(HGNC)
    resolved, renamed, zero = {}, 0, 0
    for gene in sorted(universe):
        if gene in vectors:
            resolved[gene] = vectors[gene]
            continue
        hit = next((a for a in aliases.get(gene, ()) if a in vectors), None)
        if hit:
            resolved[gene] = vectors[hit]
            renamed += 1
        else:
            resolved[gene] = ["0"] * width
            zero += 1
    print("  direct        : {}".format(len(universe) - renamed - zero))
    print("  via alias     : {}".format(renamed))
    print("  zero-filled   : {}  ({:.0f}%)".format(
        zero, 100 * zero / len(universe)))

    os.makedirs(args.out_dir, exist_ok=True)
    pm_path = os.path.join(args.out_dir, "pubmed_biogrid_384d.txt")
    with open(pm_path, "w") as handle:
        for gene in sorted(resolved):
            handle.write(gene + " " + " ".join(resolved[gene]) + "\n")
    print("\nWrote {}".format(pm_path))

    # Random control, matched in shape AND in which genes are zero - so the
    # only difference from the PubMed matrix is whether the non-zero values
    # carry literature signal.
    rng = random.Random(args.seed)
    rnd_path = os.path.join(args.out_dir, "random_biogrid_384d.txt")
    with open(rnd_path, "w") as handle:
        for gene in sorted(resolved):
            if all(v == "0" for v in resolved[gene]):
                row = ["0"] * width
            else:
                row = ["{:.6f}".format(rng.gauss(0, 1)) for _ in range(width)]
            handle.write(gene + " " + " ".join(row) + "\n")
    print("Wrote {}  (capacity control)".format(rnd_path))


if __name__ == "__main__":
    main()
