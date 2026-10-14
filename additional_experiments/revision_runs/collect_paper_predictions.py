"""
Collect the per-gene predictions behind the manuscript's Table 1.

Runs on Spartan against the original experiment directory
(/data/projects/punim0512/chathura_projects/Speos_latest/results), averages each
experiment's outer/inner fold files into one per-gene table, and writes 27 small
TSVs that can be copied back to a laptop for the revision analyses.

Which 27 is decided by additional_experiments/revision_runs/experiment_lookup.tsv,
built by matching Table 1's median ranks against results/GNN_results/rank_metrics.tsv.

WHY NOT JUST USE summarize_output_probabilities.py
--------------------------------------------------
That script selects fold files with

    file.startswith(experiment)

which has no delimiter, so summarising "ExpC9" also sweeps in every file
belonging to ExpC90...ExpC97, and "ExpC7" sweeps in ExpC70...ExpC73. Both of
those are real experiments present in rank_metrics.tsv, and both of the affected
IDs are cited by Table 1 (ExpC7 = Microcephaly GNN, ExpC9 = Cerebral Palsy GNN).
Averaging across experiments would blend unrelated models into one ranking.

This script matches on `experiment + "_"` instead, which is unambiguous because
fold files are named <Exp>_<adjacency>_outer_<i>_fold_<j>.tsv.

It also reports, per experiment, how many files the old prefix rule WOULD have
matched. Where that count differs from the strict count, the published number
for that experiment may have been computed over a contaminated file set. The
decisive test is downstream: re-run evaluate_results.py on the strict output and
compare the median rank against Table 1. A match means the original run was
clean (the colliding experiments probably did not exist yet when it was
summarised); a mismatch means that cell of Table 1 needs revisiting.

Usage on Spartan, from the KIML root:

    python additional_experiments/revision_runs/collect_paper_predictions.py \
        --results-dir /data/projects/punim0512/chathura_projects/Speos_latest/results \
        --out-dir additional_experiments/revision_runs/paper_predictions

Then copy back just that directory (~16 MB).
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

REQUIRED = {"hgnc", "truth", "prediction", "probability"}


def load_lookup(path):
    with open(path) as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def average_experiment(results_dir, experiment):
    """Average prediction/probability per gene across an experiment's fold files.

    Mirrors summarize_output_probabilities.py, but with delimiter-anchored
    matching so sibling experiments sharing a numeric prefix are excluded.
    """
    everything = os.listdir(results_dir)
    strict = sorted(f for f in everything
                    if f.startswith(experiment + "_") and f.endswith(".tsv"))
    loose = sorted(f for f in everything
                   if f.startswith(experiment) and f.endswith(".tsv"))

    totals = defaultdict(lambda: {"truth": None, "prediction": 0.0,
                                  "probability": 0.0, "n": 0})
    skipped = []
    for name in strict:
        path = os.path.join(results_dir, name)
        with open(path, newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
                skipped.append(name)
                continue
            for row in reader:
                gene = row["hgnc"]
                try:
                    prediction = float(row["prediction"])
                    probability = float(row["probability"])
                except (TypeError, ValueError):
                    continue
                record = totals[gene]
                if record["truth"] is None:
                    record["truth"] = row["truth"]
                record["prediction"] += prediction
                record["probability"] += probability
                record["n"] += 1

    rows = [{"hgnc": gene,
             "truth": rec["truth"],
             "avg_prediction": rec["prediction"] / rec["n"],
             "avg_probability": rec["probability"] / rec["n"]}
            for gene, rec in totals.items() if rec["n"]]
    return rows, strict, loose, skipped


def main():
    here = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results-dir", required=True,
                        help="the ORIGINAL experiment results directory")
    parser.add_argument("--lookup", default=os.path.join(here, "experiment_lookup.tsv"))
    parser.add_argument("--out-dir", default=os.path.join(here, "paper_predictions"))
    args = parser.parse_args()

    if not os.path.isdir(args.results_dir):
        sys.exit("No such directory: {}".format(args.results_dir))
    os.makedirs(args.out_dir, exist_ok=True)

    lookup = load_lookup(args.lookup)
    print("Collecting {} experiments from {}\n".format(len(lookup), args.results_dir))

    collisions, missing = [], []
    print("{:26}{:9}{:>10}{:>8}{:>9}{:>8}".format(
        "disease", "variant", "experiment", "files", "genes", "loose"))
    for entry in lookup:
        experiment = entry["experiment_id"]
        rows, strict, loose, skipped = average_experiment(args.results_dir, experiment)

        if not rows:
            missing.append(experiment)
            print("{:26}{:9}{:>10}{:>8}{:>9}{:>8}   <-- NO FILES".format(
                entry["disease"], entry["paper_variant"], experiment, len(strict), 0, len(loose)))
            continue

        out_path = os.path.join(args.out_dir, "{}_probabilities.tsv".format(experiment))
        with open(out_path, "w", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["hgnc", "truth", "avg_prediction", "avg_probability"],
                delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

        flag = ""
        if len(loose) != len(strict):
            collisions.append((experiment, len(strict), len(loose)))
            flag = "   <-- PREFIX COLLISION"
        if skipped:
            flag += "  [{} files lacked required columns]".format(len(skipped))
        print("{:26}{:9}{:>10}{:>8}{:>9}{:>8}{}".format(
            entry["disease"], entry["paper_variant"], experiment,
            len(strict), len(rows), len(loose), flag))

    print("\nWrote {} files to {}".format(len(lookup) - len(missing), args.out_dir))

    if missing:
        print("\n[ERROR] No fold files found for: {}".format(", ".join(missing)))
        print("        Check the naming in {} before copying anything back.".format(
            args.results_dir))

    if collisions:
        print("\n" + "=" * 70)
        print(" PREFIX COLLISIONS - the published numbers for these may be affected")
        print("=" * 70)
        for experiment, n_strict, n_loose in collisions:
            print("  {:8} strict {:>4} files, old prefix rule would take {:>4}".format(
                experiment, n_strict, n_loose))
        print("\n  These were summarised by the original script using a prefix match with")
        print("  no delimiter, so sibling experiments may have been averaged in. To test")
        print("  whether it actually mattered, re-evaluate the strict output and compare")
        print("  the median rank against Table 1:")
        print()
        for experiment, _, _ in collisions:
            print("    python results_processing/evaluate_results.py -e {} -d <disease> \\".format(experiment))
            print("        --summary rank_metrics_check.tsv")
        print()
        print("  Table 1 says: ExpC7 (Microcephaly GNN) = 4748, ExpC9 (Cerebral Palsy GNN) = 3338.")
        print("  Match  -> the original summarisation was clean; nothing to do.")
        print("  Differ -> that cell of Table 1 was computed over a blended file set.")
        print("=" * 70)


if __name__ == "__main__":
    main()
