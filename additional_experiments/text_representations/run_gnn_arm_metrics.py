"""
R1.4 at the GNN level: does the sentence transformer beat classical text?

Reviewer 1 comment 4 asks whether the MiniLM embeddings are doing something a
classical text representation could not. run_model_classes.py answers that for
four plain classifiers; this answers it for the actual KI-GNN architecture,
which is the configuration the manuscript's claims rest on.

Each arm is identical to KI-GNN except the literature matrix:

    MiniLM        pubmed_embeddings_rearranged_2022_09   (the published arm)
    TF-IDF full   TF-IDF + SVD to the same 384 dims, titles AND abstracts
    TF-IDF title  the same, titles only
    Doc2Vec       learned and dense like MiniLM, but trained only on the
                  cutoff-restricted corpus

THE BASELINE IS THE Rev_ MiniLM RUN, NOT THE PUBLISHED ONE. SPEOS never calls
torch.manual_seed, so two runs of the same configuration differ. Comparing a
new TF-IDF run against the published MiniLM number would confound the
representation with run-to-run variance; Rev_<disease>_KIGNN_s1 was produced by
the same pipeline in the same batch, so the literature matrix is the only
difference.

Contrasts are paired: every arm ranks the same post-cutoff target genes, so
comparing marginal intervals would be the wrong test.

Usage:
    python additional_experiments/text_representations/run_gnn_arm_metrics.py
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REVISION = os.path.join(ROOT, "additional_experiments", "revision_runs")
sys.path.insert(0, REVISION)
from revision_analysis import (bootstrap, load_predictions,  # noqa: E402
                               paired_bootstrap, rank_unseen)

PREDICTIONS = os.path.join(REVISION, "paper_predictions")
DISEASES_DIR = os.path.join(ROOT, "data", "kiml_data", "diseases")

DISEASES = {
    "dee": "DEE-2025_03_vs_2022_09.txt",
    "cp": "CP-2025_06_vs_2022_09.txt",
}

# label -> Rev_ variant suffix. MiniLM first: it is the reference.
ARMS = [
    ("MiniLM (published)", "KIGNN"),
    ("TF-IDF full", "KIGNN-TFIDF"),
    ("TF-IDF title", "KIGNN-TFIDF-TITLE"),
    ("Doc2Vec", "KIGNN-DOC2VEC"),
]
REFERENCE = "MiniLM (published)"


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
                        default=os.path.join(HERE, "gnn_arm_metrics.tsv"))
    args = parser.parse_args()

    results, contrasts = [], []
    print("{:8}{:22}{:>9}{:>10}  {}".format(
        "disease", "representation", "targets", "median", "95% CI"))
    print("-" * 70)

    for disease, target_file in DISEASES.items():
        targets = read_genes(os.path.join(DISEASES_DIR, target_file))
        ranks, universes = {}, {}

        for label, variant in ARMS:
            name = "Rev_{}_{}_{}_probabilities.tsv".format(
                disease, variant, args.seed_tag)
            path = os.path.join(PREDICTIONS, name)
            if not os.path.exists(path):
                print("{:8}{:22}  (not yet run)".format(disease, label))
                continue

            all_ranks, universe = rank_unseen(load_predictions(path))
            hit = {g: all_ranks[g] for g in sorted(targets) if g in all_ranks}
            ranks[label] = hit
            universes[label] = universe

            point, bounds = bootstrap(list(hit.values()), universe,
                                      args.n_boot, args.seed)
            record = {"disease": disease, "representation": label,
                      "experiment": name.replace("_probabilities.tsv", ""),
                      "n_targets": len(hit), "universe_size": universe,
                      "n_boot": args.n_boot}
            for key, value in point.items():
                record[key] = round(value, 4)
                if key in bounds:
                    record[key + "_lo"] = round(bounds[key][0], 4)
                    record[key + "_hi"] = round(bounds[key][1], 4)
            results.append(record)

            ci = bounds.get("median_rank_unseen")
            print("{:8}{:22}{:>9}{:>10}  {}".format(
                disease, label, len(hit),
                "{:g}".format(point["median_rank_unseen"]),
                "[{:g}, {:g}]".format(*ci) if ci else "-"))

        for label in ranks:
            if label == REFERENCE or REFERENCE not in ranks:
                continue
            out, n = paired_bootstrap(
                ranks[label], ranks[REFERENCE],
                universes[label], universes[REFERENCE], args.n_boot, args.seed)
            if not out:
                continue
            record = {"disease": disease, "A": label, "B": REFERENCE,
                      "n_shared_targets": n}
            for key, (diff, lo, hi, sig) in out.items():
                record[key] = round(diff, 4)
                record[key + "_lo"] = round(lo, 4)
                record[key + "_hi"] = round(hi, 4)
                record[key + "_significant"] = sig
            contrasts.append(record)

    if contrasts:
        print("\nPaired against {} (negative = classical ranks targets higher)"
              .format(REFERENCE))
        print("{:8}{:22}{:>24}{:>6}".format(
            "disease", "representation", "difference [95% CI]", "sig"))
        print("-" * 62)
        for r in contrasts:
            key = "median_rank_unseen"
            print("{:8}{:22}{:>24}{:>6}".format(
                r["disease"], r["A"],
                "{:+.0f} [{:+.0f}, {:+.0f}]".format(
                    r[key], r[key + "_lo"], r[key + "_hi"]),
                "yes" if r[key + "_significant"] else "no"))

        cols = []
        for r in contrasts:
            for k in r:
                if k not in cols:
                    cols.append(k)
        contrast_path = args.out.replace(".tsv", "_contrasts.tsv")
        with open(contrast_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=cols, delimiter="\t")
            writer.writeheader()
            writer.writerows(contrasts)
        print("\nWrote {} contrasts -> {}".format(len(contrasts), contrast_path))

    cols = []
    for r in results:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    print("Wrote {} rows -> {}".format(len(results), args.out))


if __name__ == "__main__":
    main()
