"""
R1.5b and R1.5e at the SPEOS level, from the Rev_ runs.

Two of Reviewer 1's five sub-ablations are answerable by reconfiguring SPEOS
itself rather than by a surrogate model:

  R1.5b  "PubMed node features versus KG edges within KI-GNN"
         KI-GNN differs from GNN in TWO ways at once - it adds literature node
         features AND swaps the PPI graph for the knowledge graph. Changing
         both together cannot attribute the gain. These four runs form a 2x2:

                          PPI graph        KG graph
             LL features  GNN              GNN-KG
             LL+HL        KIGNN-PPI        KIGNN

  R1.5e  "GNN message passing versus a non-graph model using exactly the same
         node features"
         KIMLP sets mp.n_layers to 0, so GeneNetwork's forward() reduces to
         pre_mp -> post_mp. Features, pre/post depth and width, training and
         folds are identical to KIGNN, so message passing is the only variable.
         The shipped FCNN class is unusable for this: get_architecture calls
         FCNN(config, dim) while its __init__ takes only input_dim, and even
         once fixed it hardcodes 50 layers of width 70 against KIGNN's 5+2+5 of
         width 50, which would confound depth and width with the graph.

All contrasts are paired on the shared target genes. These are real SPEOS runs,
so unlike the minimal GCN in fusion/ the numbers ARE comparable with Table 1 -
subject to run-to-run variance, since SPEOS never calls torch.manual_seed.

Usage:
    python additional_experiments/revision_runs/run_speos_ablation_metrics.py
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from revision_analysis import (bootstrap, load_predictions,  # noqa: E402
                               paired_bootstrap, rank_unseen)

PREDICTIONS = os.path.join(HERE, "paper_predictions")
DISEASES_DIR = os.path.join(ROOT, "data", "kiml_data", "diseases")

TARGETS = {
    "dee": "DEE-2025_03_vs_2022_09.txt",
    "cp": "CP-2025_06_vs_2022_09.txt",
    "intellectual_disability": "Intellectual-disability-2025_06_vs_2022_09.txt",
}

# variant -> (label, node features, graph)
VARIANTS = {
    "GNN": ("GNN", "LL", "PPI"),
    "GNN-KG": ("GNN-KG", "LL", "KG"),
    "KIGNN-PPI": ("KI-GNN on PPI", "LL+HL", "PPI"),
    "KIGNN": ("KI-GNN", "LL+HL", "KG"),
    "KIMLP": ("KI-MLP (no message passing)", "LL+HL", "none"),
}

# (A, B, what it isolates, which sub-ablation)
CONTRASTS = [
    ("GNN-KG", "GNN", "graph: KG vs PPI, with LL features only", "R1.5b"),
    ("KIGNN", "KIGNN-PPI", "graph: KG vs PPI, with LL+HL features", "R1.5b"),
    ("KIGNN-PPI", "GNN", "features: +literature, on the PPI graph", "R1.5b"),
    ("KIGNN", "GNN-KG", "features: +literature, on the KG", "R1.5b"),
    ("KIGNN", "GNN", "both at once (the published comparison)", "reference"),
    ("KIMLP", "KIGNN", "message passing removed, features identical", "R1.5e"),
]


def read_genes(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed-tag", default="s1")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "speos_ablation_metrics.tsv"))
    args = parser.parse_args()

    metrics, contrasts = [], []
    print("{:26}{:28}{:>8}{:>10}  {}".format(
        "disease", "configuration", "targets", "median", "95% CI"))
    print("-" * 84)

    for disease, target_file in TARGETS.items():
        targets = read_genes(os.path.join(DISEASES_DIR, target_file))
        ranks, universes = {}, {}

        for variant, (label, features, graph) in VARIANTS.items():
            path = os.path.join(PREDICTIONS, "Rev_{}_{}_{}_probabilities.tsv".format(
                disease, variant, args.seed_tag))
            if not os.path.exists(path):
                continue
            all_ranks, universe = rank_unseen(load_predictions(path))
            hit = {g: all_ranks[g] for g in sorted(targets) if g in all_ranks}
            ranks[variant], universes[variant] = hit, universe

            point, bounds = bootstrap(list(hit.values()), universe,
                                      args.n_boot, args.seed)
            record = {"disease": disease, "variant": variant, "label": label,
                      "node_features": features, "graph": graph,
                      "n_targets": len(hit), "universe_size": universe,
                      "n_boot": args.n_boot}
            for key, value in point.items():
                record[key] = round(value, 4)
                if key in bounds:
                    record[key + "_lo"] = round(bounds[key][0], 4)
                    record[key + "_hi"] = round(bounds[key][1], 4)
            metrics.append(record)

            cib = bounds.get("median_rank_unseen")
            print("{:26}{:28}{:>8}{:>10}  {}".format(
                disease, label, len(hit),
                "{:g}".format(point["median_rank_unseen"]),
                "[{:g}, {:g}]".format(*cib) if cib else "-"))

        for a, b, isolates, which in CONTRASTS:
            if a not in ranks or b not in ranks:
                continue
            out, n = paired_bootstrap(ranks[a], ranks[b], universes[a],
                                      universes[b], args.n_boot, args.seed)
            if not out:
                continue
            record = {"disease": disease, "sub_ablation": which,
                      "A": VARIANTS[a][0], "B": VARIANTS[b][0],
                      "isolates": isolates, "n_shared_targets": n}
            for key, (diff, lo, hi, s) in out.items():
                record[key] = round(diff, 4)
                record[key + "_lo"] = round(lo, 4)
                record[key + "_hi"] = round(hi, 4)
                record[key + "_significant"] = s
            contrasts.append(record)

    print("\nPaired contrasts (negative = A ranks targets higher than B)")
    print("{:26}{:9}{:44}{:>22}{:>6}".format(
        "disease", "ablation", "isolates", "difference [95% CI]", "sig"))
    print("-" * 108)
    for r in contrasts:
        key = "median_rank_unseen"
        print("{:26}{:9}{:44}{:>22}{:>6}".format(
            r["disease"], r["sub_ablation"], r["isolates"],
            "{:+.0f} [{:+.0f}, {:+.0f}]".format(
                r[key], r[key + "_lo"], r[key + "_hi"]),
            "yes" if r[key + "_significant"] else "no"))

    for rows, path in ((metrics, args.out),
                       (contrasts, args.out.replace(".tsv", "_contrasts.tsv"))):
        if not rows:
            continue
        cols = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=cols, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        print("\nWrote {} rows -> {}".format(len(rows), path))


if __name__ == "__main__":
    main()
