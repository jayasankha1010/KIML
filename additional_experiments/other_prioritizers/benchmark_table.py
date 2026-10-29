"""
Benchmark table: how do existing prioritisers do, against KIML? (R1.8 / R3.2)

This serves the SECOND of the rebuttal's two arguments, and only that one.

  1. The ablation family - the same architecture trained on experimental data,
     on knowledge, and on both - exists to show that knowledge improves gene
     prioritisation. That argument lives in fusion/ and model_classes/.

  2. This file: how well do EXISTING published methods do, and where does KIML
     sit among them? ToppGene is an existing method, nothing more. SPEOS and
     Mantis appear in both arguments - here they are the published methods in
     their own right, which means SPEOS = GNN and Mantis = RF, each using the
     experimental data they were published with.

The knowledge-only arms (C-GNN, C-RF) are NOT comparators. They are ablation
variants belonging to argument 1, so they are excluded from this table; they
remain in toppgene_vs_kiml_contrasts.tsv for diagnostic use.

Every method is scored on a COMMON target set per disease - the targets every
method in the table can rank - so the columns are directly comparable. That is
stricter than the pairwise contrasts, which each use their own shared set.

Usage:
    python additional_experiments/other_prioritizers/benchmark_table.py
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
MANTIS_LOOKUP = os.path.join(REVISION, "mantis_lookup.tsv")
MANTIS_PREDICTIONS = os.path.join(ROOT, "external", "Mantis", "mantis_results")

# Existing published methods, then KIML's own. "GNN" is SPEOS as published and
# "RF" is Mantis as published - the same runs, read as comparators rather than
# as the experimental-data arm of an ablation.
EXISTING = [("ToppGene", None), ("SPEOS", "GNN"), ("Mantis", "RF")]
OURS = [("KI-GNN", "KI-GNN"), ("KI-RF", "KI-RF")]


# Multi-seed runs, named <prefix>_<disease>_<variant>_s<seed>. Neither
# pipeline is seeded internally, so a single run is one draw; these are all of
# them.
SEED_RUNS = {
    "GNN": (PREDICTIONS, "Rev_{disease}_GNN_s{seed}_probabilities.tsv"),
    "KI-GNN": (PREDICTIONS, "Rev_{disease}_KIGNN_s{seed}_probabilities.tsv"),
    "RF": (os.path.join(ROOT, "external", "Mantis", "Mantis_Out"),
           "Mantis_{disease}_RF_s{seed}/Gene-Predictions/"
           "RandomForestClassifier.mantis-ml_predictions.csv"),
    "KI-RF": (os.path.join(ROOT, "external", "Mantis", "Mantis_Out"),
              "Mantis_{disease}_KI-RF_s{seed}/Gene-Predictions/"
              "RandomForestClassifier.mantis-ml_predictions.csv"),
}
MAX_SEEDS = 5


def consensus_ranking(folder, template, disease):
    """Average each gene's rank across the available seeds.

    The benchmark used to read one published prediction file per method, but
    those are single unseeded draws - and we now know several do not
    reproduce (platelet-disorder SPEOS was published at 6988; five reruns give
    [1611, 2926]). Quoting them here would also contradict the multi-seed tab.

    Averaging per-gene RANKS, rather than taking a mean of per-seed medians,
    keeps a full ranking - which the common-target-set intersection and the
    paired bootstrap both need. The cost is that the median of these averaged
    ranks is not identical to the mean of the per-seed medians reported
    elsewhere; they answer slightly different questions and will differ a
    little.
    """
    totals, counts, universes = {}, {}, []
    for seed in range(1, MAX_SEEDS + 1):
        path = os.path.join(folder, template.format(disease=disease, seed=seed))
        if not os.path.exists(path):
            continue
        ranks, universe = rank_unseen(load_predictions(path))
        universes.append(universe)
        for gene, rank in ranks.items():
            totals[gene] = totals.get(gene, 0) + rank
            counts[gene] = counts.get(gene, 0) + 1
    if not totals:
        return None, None, 0
    # Keep genes every available seed ranked, so no gene is averaged over a
    # different number of runs than its neighbours.
    n_seeds = max(counts.values())
    mean_rank = {g: totals[g] / counts[g] for g in totals if counts[g] == n_seeds}
    return mean_rank, max(universes), n_seeds


def load_kiml():
    """disease -> arm -> consensus per-gene ranks, averaged over seeds."""
    ranks, universe, seeds = {}, {}, {}
    wanted = [a for _, a in EXISTING if a] + [a for _, a in OURS]
    diseases = sorted({d for d, _, _ in
                       [(x[0], None, None) for x in MAPPING.values()]})
    for arm in wanted:
        if arm not in SEED_RUNS:
            continue
        folder, template = SEED_RUNS[arm]
        for disease in diseases:
            mean_rank, n, n_seeds = consensus_ranking(folder, template, disease)
            if mean_rank is None:
                continue
            ranks.setdefault(disease, {})[arm] = mean_rank
            universe.setdefault(disease, {})[arm] = n
            seeds.setdefault(disease, {})[arm] = n_seeds
    return ranks, universe, seeds


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "benchmark_existing_methods.tsv"))
    args = parser.parse_args()

    kiml, kiml_universe, kiml_seeds = load_kiml()
    columns = EXISTING + OURS

    rows = []
    header = "{:24}{:>8}".format("disease", "targets")
    for label, _ in columns:
        header += "{:>10}".format(label)
    print(header)
    print("-" * len(header))

    for filename, (disease, seed_file, target_file) in sorted(MAPPING.items()):
        path = os.path.join(HERE, "toppgene", filename)
        if not os.path.exists(path) or disease not in kiml:
            continue

        ranking = load_ranking(path)
        seeds = read_genes(os.path.join(DISEASES_DIR, seed_file))
        targets = read_genes(os.path.join(DISEASES_DIR, target_file))
        if seeds and len(seeds & set(ranking)) / len(seeds) > SEED_LEAK_LIMIT:
            continue
        for gene in seeds & set(ranking):
            ranking.pop(gene, None)

        per_method, universes = {"ToppGene": ranking}, {"ToppGene": len(ranking)}
        missing = False
        for label, arm in columns:
            if arm is None:
                continue
            if arm not in kiml[disease]:
                missing = True
                break
            per_method[label] = kiml[disease][arm]
            universes[label] = kiml_universe[disease][arm]
        if missing:
            continue

        # Common target set: every method in the table must be able to rank it.
        common = sorted(targets.intersection(*(set(r) for r in per_method.values())))
        if not common:
            continue

        line = "{:24}{:>8}".format(disease, len(common))
        record = {"disease": disease, "n_common_targets": len(common)}
        for label, arm in columns:
            if arm:
                record[label + "_n_seeds"] = kiml_seeds.get(disease, {}).get(arm, 0)
        for label, _ in columns:
            med = sorted(per_method[label][g] for g in common)[len(common) // 2]
            line += "{:>10}".format(med)
            record[label + "_median"] = med
            record[label + "_universe"] = universes[label]
            record[label + "_percentile"] = round(med / universes[label], 4)
        print(line)

        # Significance against the best existing method on this disease.
        best_label = min((l for l, _ in EXISTING),
                         key=lambda l: sorted(per_method[l][g] for g in common)[len(common) // 2])
        record["best_existing"] = best_label
        for label, _ in OURS:
            out, n = paired_bootstrap(
                {g: per_method[label][g] for g in common},
                {g: per_method[best_label][g] for g in common},
                universes[label], universes[best_label], args.n_boot, args.seed)
            if not out:
                continue
            diff, lo, hi, sig = out["median_rank_unseen"]
            record[label + "_vs_best_existing"] = round(diff, 4)
            record[label + "_vs_best_existing_lo"] = round(lo, 4)
            record[label + "_vs_best_existing_hi"] = round(hi, 4)
            record[label + "_vs_best_existing_significant"] = sig
        rows.append(record)

    if not rows:
        raise SystemExit("No diseases had every method available.")

    print("\nAgainst the best EXISTING method on each disease "
          "(negative favours KIML):")
    print("{:24}{:16}{:>24}{:>6}{:>24}{:>6}".format(
        "disease", "best existing", "KI-GNN diff [95% CI]", "sig",
        "KI-RF diff [95% CI]", "sig"))
    for r in rows:
        cells = ""
        for label, _ in OURS:
            key = label + "_vs_best_existing"
            if key in r:
                cells += "{:>24}{:>6}".format(
                    "{:+.0f} [{:+.0f}, {:+.0f}]".format(
                        r[key], r[key + "_lo"], r[key + "_hi"]),
                    "yes" if r[key + "_significant"] else "no")
            else:
                cells += "{:>24}{:>6}".format("-", "-")
        print("{:24}{:16}{}".format(r["disease"], r["best_existing"], cells))

    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print("\nWrote {} diseases -> {}".format(len(rows), args.out))


if __name__ == "__main__":
    main()
