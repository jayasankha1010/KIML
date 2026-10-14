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


def find_original_summary(search_dirs, experiment):
    """Locate the *_probabilities.tsv the original run produced, if it survives."""
    name = "{}_probabilities.tsv".format(experiment)
    for directory in search_dirs:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def compare_to_original(rows, original_path):
    """Compare a clean re-derivation against the original summary file.

    Returns (verdict, detail). The original is what fed Table 1, so a difference
    here means the published numbers were computed over a contaminated file set.
    """
    clean = {r["hgnc"]: r["avg_probability"] for r in rows}
    original = {}
    with open(original_path, newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            try:
                original[row["hgnc"]] = float(row["avg_probability"])
            except (TypeError, ValueError, KeyError):
                continue

    if not original:
        return "unreadable", "could not parse avg_probability"

    shared = set(clean) & set(original)
    if not shared:
        return "disjoint", "no overlapping genes"

    worst = max(abs(clean[g] - original[g]) for g in shared)
    only_clean = len(set(clean) - set(original))
    only_orig = len(set(original) - set(clean))

    detail = "max|diff|={:.2e}  shared {}/{}  clean-only {}  orig-only {}".format(
        worst, len(shared), len(clean), only_clean, only_orig)

    # Float formatting on write loses precision, so allow a small tolerance.
    if worst < 1e-6 and not only_clean and not only_orig:
        return "identical", detail
    return "DIFFERS", detail


def average_experiment(results_dir, experiment):
    """Average prediction/probability per gene across an experiment's fold files.

    Mirrors summarize_output_probabilities.py, but with delimiter-anchored
    matching so sibling experiments sharing a numeric prefix are excluded.
    """
    everything = os.listdir(results_dir)
    # Anchor on the separator, but don't double it for IDs that already end in
    # "_" (e.g. ExpCP_), or nothing matches.
    prefix = experiment if experiment.endswith("_") else experiment + "_"
    strict = sorted(f for f in everything
                    if f.startswith(prefix) and f.endswith(".tsv"))
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
    parser.add_argument("--original-dirs", nargs="*", default=None,
                        help="directories holding the ORIGINAL *_probabilities.tsv files "
                             "(defaults to <results-dir>/../results_processing and its "
                             "old_results subdirectory). These are what fed Table 1, so "
                             "comparing against them settles whether the prefix collision "
                             "affected the published numbers.")
    args = parser.parse_args()

    if not os.path.isdir(args.results_dir):
        sys.exit("No such directory: {}".format(args.results_dir))
    os.makedirs(args.out_dir, exist_ok=True)

    if args.original_dirs is None:
        parent = os.path.dirname(os.path.abspath(args.results_dir))
        args.original_dirs = [os.path.join(parent, "results_processing"),
                              os.path.join(parent, "results_processing", "old_results")]
    present = [d for d in args.original_dirs if os.path.isdir(d)]
    if present:
        print("Comparing against original summaries in:")
        for directory in present:
            print("  {}".format(directory))
    else:
        print("[warn] no original *_probabilities.tsv directories found; the published")
        print("       numbers cannot be checked against clean re-derivations.")

    lookup = load_lookup(args.lookup)
    print("\nCollecting {} experiments from {}\n".format(len(lookup), args.results_dir))

    collisions, missing, contaminated, unchecked = [], [], [], []
    print("{:24}{:8}{:>9}{:>7}{:>8}{:>7}  {}".format(
        "disease", "variant", "experiment", "files", "genes", "loose", "vs original"))
    for entry in lookup:
        experiment = entry["experiment_id"]
        rows, strict, loose, skipped = average_experiment(args.results_dir, experiment)

        if not rows:
            missing.append(experiment)
            print("{:24}{:8}{:>9}{:>7}{:>8}{:>7}  <-- NO FILES".format(
                entry["disease"], entry["paper_variant"], experiment, len(strict), 0, len(loose)))
            continue

        out_path = os.path.join(args.out_dir, "{}_probabilities.tsv".format(experiment))
        with open(out_path, "w", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["hgnc", "truth", "avg_prediction", "avg_probability"],
                delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

        if len(loose) != len(strict):
            collisions.append((experiment, len(strict), len(loose)))

        # The decisive check: does our clean re-derivation match the summary
        # file the original run produced (and that Table 1 was computed from)?
        original = find_original_summary(present, experiment)
        if original is None:
            verdict, detail = "not found", ""
            unchecked.append(experiment)
        else:
            verdict, detail = compare_to_original(rows, original)
            if verdict == "DIFFERS":
                contaminated.append((experiment, entry["disease"],
                                     entry["paper_variant"], original, detail))

        print("{:24}{:8}{:>9}{:>7}{:>8}{:>7}  {}{}".format(
            entry["disease"], entry["paper_variant"], experiment,
            len(strict), len(rows), len(loose), verdict,
            "   <-- PREFIX COLLISION" if len(loose) != len(strict) else ""))
        if skipped:
            print("{:>72}[{} files lacked required columns]".format("", len(skipped)))

    print("\nWrote {} files to {}".format(len(lookup) - len(missing), args.out_dir))

    if missing:
        print("\n[ERROR] No fold files found for: {}".format(", ".join(missing)))
        print("        Check the naming in {} before copying anything back.".format(
            args.results_dir))

    if collisions:
        print("\n{} experiment(s) had a prefix collision: {}".format(
            len(collisions), ", ".join(e for e, _, _ in collisions)))

    print("\n" + "=" * 72)
    if contaminated:
        print(" PUBLISHED NUMBERS AFFECTED - clean re-derivation differs from the")
        print(" summary file the original run produced")
        print("=" * 72)
        for experiment, disease, variant, path, detail in contaminated:
            print("  {:8} {:24} {:8}".format(experiment, disease, variant))
            print("           original: {}".format(path))
            print("           {}".format(detail))
        print("\n  Table 1 and any text quoting these cells need recomputing from the")
        print("  clean files in the output directory.")
    elif unchecked and len(unchecked) == len(lookup):
        print(" NOT CHECKED - no original summary files were found, so whether the")
        print(" prefix collision affected Table 1 remains unknown.")
    else:
        print(" ALL CHECKED EXPERIMENTS MATCH their original summary files.")
        print(" The prefix collision did not affect the published numbers - the")
        print(" colliding experiments post-date the original summarisation.")
        if unchecked:
            print("\n Could not check (no original summary found): {}".format(
                ", ".join(unchecked)))
    print("=" * 72)


if __name__ == "__main__":
    main()
