"""
ToppGene against KIML, paired on the same target genes (R1.8 / R3.2).

The marginal numbers in toppgene_metrics.tsv cannot be compared directly with
Table 1: ToppGene ranks over ~14.9k genes and KIML over ~16.5k, so a raw median
rank rewards whichever method ranks over fewer genes. This pairs them instead -
same disease, same target genes, bootstrap the difference - and additionally
reports the rank as a percentile of each method's own universe, which is the
scale-free version of the same comparison.

Targets ToppGene cannot return at all are excluded from the paired test, since
a difference is undefined for them. They are counted and reported, because
dropping them silently would reward ToppGene for the omission: see
run_toppgene_metrics.py, which reports the penalised variant.

Usage:
    python additional_experiments/other_prioritizers/contrast_toppgene_vs_kiml.py
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REVISION = os.path.join(ROOT, "additional_experiments", "revision_runs")
sys.path.insert(0, REVISION)
sys.path.insert(0, HERE)
from revision_analysis import load_predictions, paired_bootstrap, rank_unseen  # noqa: E402
from run_toppgene_metrics import (DISEASES_DIR, MAPPING, SEED_LEAK_LIMIT,  # noqa: E402
                                  load_ranking, read_genes)

LOOKUP = os.path.join(REVISION, "experiment_lookup.tsv")
PREDICTIONS = os.path.join(REVISION, "paper_predictions")
# The RF arm is tracked in its own lookup, pointing at the Mantis outputs.
MANTIS_LOOKUP = os.path.join(REVISION, "mantis_lookup.tsv")
MANTIS_PREDICTIONS = os.path.join(ROOT, "external", "Mantis", "mantis_results")
# All three tiers of each family. The knowledge-only arms matter most for a
# fair reading: ToppGene scores genes from GO, phenotype, pathway, PubMed and
# disease annotations, so it is itself a knowledge-only prioritiser. C-GNN and
# C-RF are its like-for-like counterparts; GNN and RF use experimental data
# only, and KI-* combine both.
ARMS = ["KI-GNN", "KI-RF", "C-GNN", "C-RF", "GNN", "RF"]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "toppgene_vs_kiml_contrasts.tsv"))
    args = parser.parse_args()

    # disease -> arm -> per-gene ranks over that arm's own universe
    kiml, kiml_universe = {}, {}
    with open(LOOKUP) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["paper_variant"] not in ARMS:
                continue
            path = os.path.join(PREDICTIONS,
                                os.path.basename(row["probabilities_file"]))
            if not os.path.exists(path):
                continue
            ranks, universe = rank_unseen(load_predictions(path))
            kiml.setdefault(row["disease"], {})[row["paper_variant"]] = ranks
            kiml_universe.setdefault(row["disease"], {})[row["paper_variant"]] = universe

    if os.path.exists(MANTIS_LOOKUP):
        with open(MANTIS_LOOKUP) as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["paper_variant"] not in ARMS:
                    continue
                path = os.path.join(MANTIS_PREDICTIONS,
                                    os.path.basename(row["predictions_file"]))
                if not os.path.exists(path):
                    continue
                ranks, universe = rank_unseen(load_predictions(path))
                kiml.setdefault(row["disease"], {})[row["paper_variant"]] = ranks
                kiml_universe.setdefault(row["disease"], {})[row["paper_variant"]] = universe

    results = []
    print("{:22}{:10}{:>8}{:>10}{:>10}{:>22}{:>6}".format(
        "disease", "vs", "shared", "ToppGene", "KIML", "difference [95% CI]", "sig"))
    print("-" * 90)

    for filename, (disease, seed_file, target_file) in sorted(MAPPING.items()):
        path = os.path.join(HERE, "toppgene", filename)
        if not os.path.exists(path) or disease not in kiml:
            continue

        ranking = load_ranking(path)
        seeds = read_genes(os.path.join(DISEASES_DIR, seed_file))
        targets = read_genes(os.path.join(DISEASES_DIR, target_file))
        leaked = seeds & set(ranking)
        if seeds and len(leaked) / len(seeds) > SEED_LEAK_LIMIT:
            continue
        for gene in leaked:
            ranking.pop(gene, None)

        tg_ranks = {g: ranking[g] for g in targets if g in ranking}
        tg_universe = len(ranking)

        for arm in ARMS:
            if arm not in kiml[disease]:
                continue
            arm_ranks = {g: r for g, r in kiml[disease][arm].items() if g in targets}
            arm_universe = kiml_universe[disease][arm]

            out, n = paired_bootstrap(tg_ranks, arm_ranks,
                                      tg_universe, arm_universe,
                                      args.n_boot, args.seed)
            if not out:
                continue
            diff, lo, hi, sig = out["median_rank_unseen"]
            shared = sorted(set(tg_ranks) & set(arm_ranks))
            tg_med = sorted(tg_ranks[g] for g in shared)[len(shared) // 2]
            arm_med = sorted(arm_ranks[g] for g in shared)[len(shared) // 2]

            print("{:22}{:10}{:>8}{:>10}{:>10}{:>22}{:>6}".format(
                disease, arm, n, tg_med, arm_med,
                "{:+.0f} [{:+.0f}, {:+.0f}]".format(diff, lo, hi),
                "yes" if sig else "no"))

            record = {"disease": disease, "comparator": "ToppGene", "kiml_arm": arm,
                      "n_shared_targets": n,
                      "n_targets_total": len(targets),
                      "n_unrankable_by_toppgene": len(targets - set(ranking)),
                      "toppgene_median": tg_med, "kiml_median": arm_med,
                      "toppgene_universe": tg_universe,
                      "kiml_universe": arm_universe,
                      "toppgene_percentile": round(tg_med / tg_universe, 4),
                      "kiml_percentile": round(arm_med / arm_universe, 4)}
            for key, (d, l, h, s) in out.items():
                record[key] = round(d, 4)
                record[key + "_lo"] = round(l, 4)
                record[key + "_hi"] = round(h, 4)
                record[key + "_significant"] = s
            results.append(record)

    if not results:
        raise SystemExit("No overlapping disease/arm pairs found.")

    columns = []
    for record in results:
        for key in record:
            if key not in columns:
                columns.append(key)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    print("\nNegative difference favours ToppGene; positive favours KIML.")
    print("Wrote {} contrasts -> {}".format(len(results), args.out))


if __name__ == "__main__":
    main()
