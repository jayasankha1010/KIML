"""
Aggregate multi-seed runs into main-table point estimates and intervals.

Reviewer 1 comment 10 asks for confidence intervals in the main results table.
The published numbers came from a single run each, and neither pipeline was
seeded - SPEOS never calls torch.manual_seed, and Mantis drew its balanced
datasets from an unseeded global RNG - so a repeat run gives a different
answer. This turns N runs per configuration into a reportable estimate.

THERE ARE TWO SOURCES OF UNCERTAINTY AND THEY ARE NOT THE SAME THING.

  seed       Retrain the model and the number moves. Measured by the spread
             ACROSS SEEDS. Everything else held fixed.
  targets    A different set of genes might have been curated after the
             cutoff. Measured by resampling TARGET GENES with the model held
             fixed. This is what every CI in the revision has reported so far.

Reporting only the first understates uncertainty on diseases with few targets;
reporting only the second understates it wherever the model is unstable (CP
GNN moved 633 ranks between two runs of one configuration). So all three are
emitted:

  seed_*      mean, sd, min, max and a t-based interval across seeds
  target_*    bootstrap over targets, averaged over seeds
  combined_*  one interval covering both, by resampling a seed AND its targets
              on every draw

Use combined_* in the paper. Keep the other two so a reviewer asking "is that
model variance or evaluation variance?" gets an answer.

Works for both arms, since they need identical treatment:

  --source gnn     Rev_<disease>_<variant>_s<seed>_probabilities.tsv
                   under revision_runs/paper_predictions/
  --source mantis  Mantis_<disease>_<arm>_s<seed>/Gene-Predictions/
                   RandomForestClassifier.mantis-ml_predictions.csv
                   under external/Mantis/Mantis_Out/

Usage:
    python additional_experiments/revision_runs/aggregate_seed_runs.py --source mantis
    python additional_experiments/revision_runs/aggregate_seed_runs.py --source gnn
"""

import argparse
import csv
import math
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from revision_analysis import (load_predictions, metrics_from_ranks,  # noqa: E402
                               rank_unseen)

DISEASES_DIR = os.path.join(ROOT, "data", "kiml_data", "diseases")
PREDICTIONS = os.path.join(HERE, "paper_predictions")
MANTIS_OUT = os.path.join(ROOT, "external", "Mantis", "Mantis_Out")

# disease -> post-split target list
TARGETS = {
    "dee": "DEE-2025_03_vs_2022_09.txt",
    "ad_dee": "AD_DEE-2022_09_to_2025_03.txt",
    "ar_dee": "AR_DEE-2022_09_to_2025_03.txt",
    "microcephaly": "Microcephaly-2025_06_vs_2022_09.txt",
    "intellectual_disability": "Intellectual-disability-2025_06_vs_2022_09.txt",
    "mnd": "MND-2025_06_vs_2022_09.txt",
    "cp": "CP-2025_06_vs_2022_09.txt",
    "platelet_disorder": "Bleeding_and_Platelet_Disorders-2026-02_vs_2022-09.txt",
    "arthrogryposis": "Arthrogryposis-2025_06_vs_2022_09.txt",
}

# source -> (arm label -> path template). Labels are the manuscript's.
SOURCES = {
    "gnn": {
        "GNN": os.path.join(PREDICTIONS, "Rev_{disease}_GNN_s{seed}_probabilities.tsv"),
        "C-GNN": os.path.join(PREDICTIONS, "Rev_{disease}_CGNN_s{seed}_probabilities.tsv"),
        "KI-GNN": os.path.join(PREDICTIONS, "Rev_{disease}_KIGNN_s{seed}_probabilities.tsv"),
    },
    "mantis": {
        arm: os.path.join(
            MANTIS_OUT, "Mantis_{disease}_" + arm + "_s{seed}",
            "Gene-Predictions", "RandomForestClassifier.mantis-ml_predictions.csv")
        for arm in ("RF", "C-RF", "KI-RF")
    },
}

# Reported in the main table. metrics_from_ranks emits more; these are the ones
# R1.10 names plus the two fold-enrichment thresholds already in the paper.
METRICS = [
    "median_rank_unseen", "mean_rank_unseen",
    "fold_enrichment_top_1_pct", "fold_enrichment_top_10_pct",
    "recall_at_10", "recall_at_50", "recall_at_100", "recall_at_250",
    "recall_at_1000",
    "precision_at_10", "precision_at_50", "precision_at_100",
    "precision_at_250", "precision_at_1000",
]

# Two-sided 95% t quantiles, df = n-1. Normal approximation is wrong at n=5.
T95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447,
       8: 2.365, 9: 2.306, 10: 2.262}


def read_genes(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def percentile_ci(values, alpha=0.05):
    if not values:
        return None, None
    values = sorted(values)
    lo = values[min(int(alpha / 2 * len(values)), len(values) - 1)]
    hi = values[min(int((1 - alpha / 2) * len(values)), len(values) - 1)]
    return lo, hi


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--diseases", nargs="*", default=sorted(TARGETS))
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1, help="RNG seed for the bootstrap")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()

    if args.out is None:
        args.out = os.path.join(HERE, "seed_aggregate_{}.tsv".format(args.source))
    arms = SOURCES[args.source]

    summary, per_seed, missing = [], [], []

    for disease in args.diseases:
        if disease not in TARGETS:
            print("[skip] unknown disease: {}".format(disease))
            continue
        targets = read_genes(os.path.join(DISEASES_DIR, TARGETS[disease]))

        for arm, template in arms.items():
            # ranks[s] = {gene: rank} for the targets this seed could rank
            ranks, universes = [], []
            for seed in range(1, args.seeds + 1):
                path = template.format(disease=disease, seed=seed)
                if not os.path.exists(path):
                    missing.append(os.path.relpath(path, ROOT))
                    continue
                all_ranks, universe = rank_unseen(load_predictions(path))
                hit = {g: all_ranks[g] for g in sorted(targets) if g in all_ranks}
                if not hit:
                    continue
                ranks.append(hit)
                universes.append(universe)

                point = metrics_from_ranks(list(hit.values()), len(hit), universe)
                row = {"disease": disease, "arm": arm, "seed": seed,
                       "n_targets": len(hit), "universe_size": universe}
                for key in METRICS:
                    value = point.get(key)
                    if value is not None and not (isinstance(value, float)
                                                  and math.isnan(value)):
                        row[key] = round(value, 6)
                per_seed.append(row)

            if not ranks:
                continue
            n = len(ranks)
            universe = universes[0]
            if len(set(universes)) > 1:
                # Different universes across seeds would make the metrics
                # incomparable; say so rather than averaging through it.
                print("[warn] {} {}: universe differs across seeds {} - "
                      "using the first".format(disease, arm, sorted(set(universes))))

            # Genes every seed could rank, so each draw compares like with like.
            shared = sorted(set.intersection(*(set(r) for r in ranks)))

            record = {"disease": disease, "arm": arm, "n_seeds": n,
                      "n_targets": len(shared), "universe_size": universe}

            per_seed_metrics = {key: [] for key in METRICS}
            for r in ranks:
                point = metrics_from_ranks([r[g] for g in shared], len(shared), universe)
                for key in METRICS:
                    value = point.get(key)
                    if value is not None and not (isinstance(value, float)
                                                  and math.isnan(value)):
                        per_seed_metrics[key].append(value)

            # Combined: resample a seed AND its targets on every draw, so the
            # interval marginalises over both sources at once.
            rng = random.Random(args.seed)
            combined = {key: [] for key in METRICS}
            m = len(shared)
            for _ in range(args.n_boot):
                r = ranks[rng.randrange(n)]
                sample = [r[shared[rng.randrange(m)]] for _ in range(m)]
                point = metrics_from_ranks(sample, m, universe)
                for key in METRICS:
                    value = point.get(key)
                    if value is not None and not (isinstance(value, float)
                                                  and math.isnan(value)):
                        combined[key].append(value)

            # Targets only: bootstrap each seed separately, average the bounds.
            target_only = {key: [[], []] for key in METRICS}
            for r in ranks:
                rng2 = random.Random(args.seed)
                draws = {key: [] for key in METRICS}
                for _ in range(args.n_boot):
                    sample = [r[shared[rng2.randrange(m)]] for _ in range(m)]
                    point = metrics_from_ranks(sample, m, universe)
                    for key in METRICS:
                        value = point.get(key)
                        if value is not None and not (isinstance(value, float)
                                                      and math.isnan(value)):
                            draws[key].append(value)
                for key in METRICS:
                    lo, hi = percentile_ci(draws[key])
                    if lo is not None:
                        target_only[key][0].append(lo)
                        target_only[key][1].append(hi)

            for key in METRICS:
                values = per_seed_metrics[key]
                if not values:
                    continue
                mean = statistics.fmean(values)
                sd = statistics.stdev(values) if len(values) > 1 else 0.0
                record[key] = round(mean, 6)
                record[key + "_seed_sd"] = round(sd, 6)
                record[key + "_seed_min"] = round(min(values), 6)
                record[key + "_seed_max"] = round(max(values), 6)
                if len(values) > 1:
                    half = T95.get(len(values), 2.0) * sd / math.sqrt(len(values))
                    record[key + "_seed_lo"] = round(mean - half, 6)
                    record[key + "_seed_hi"] = round(mean + half, 6)
                lo, hi = percentile_ci(combined[key])
                if lo is not None:
                    record[key + "_combined_lo"] = round(lo, 6)
                    record[key + "_combined_hi"] = round(hi, 6)
                los, his = target_only[key]
                if los:
                    record[key + "_target_lo"] = round(statistics.fmean(los), 6)
                    record[key + "_target_hi"] = round(statistics.fmean(his), 6)
            summary.append(record)

    if not summary:
        raise SystemExit("No runs found. Check --source and that the runs completed.")

    print("{:26}{:8}{:>7}{:>9}{:>12}{:>9}  {:24}{}".format(
        "disease", "arm", "seeds", "targets", "median rank", "seed sd",
        "combined 95% CI", "seed-only 95% CI"))
    print("-" * 118)
    for r in sorted(summary, key=lambda x: (x["disease"], x["arm"])):
        key = "median_rank_unseen"
        if key not in r:
            continue
        print("{:26}{:8}{:>7}{:>9}{:>12.1f}{:>9.1f}  {:24}{}".format(
            r["disease"], r["arm"], r["n_seeds"], r["n_targets"], r[key],
            r.get(key + "_seed_sd", 0.0),
            "[{:.0f}, {:.0f}]".format(r.get(key + "_combined_lo", float("nan")),
                                      r.get(key + "_combined_hi", float("nan"))),
            "[{:.0f}, {:.0f}]".format(r.get(key + "_seed_lo", float("nan")),
                                      r.get(key + "_seed_hi", float("nan")))
            if key + "_seed_lo" in r else "-"))

    for rows, path in ((summary, args.out),
                       (per_seed, args.out.replace(".tsv", "_per_seed.tsv"))):
        columns = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        print("\nWrote {} rows -> {}".format(len(rows), path))

    if missing:
        print("\n[warn] {} run(s) missing - aggregates use what exists:".format(len(missing)))
        for path in missing[:12]:
            print("   {}".format(path))
        if len(missing) > 12:
            print("   ... and {} more".format(len(missing) - 12))


if __name__ == "__main__":
    main()
