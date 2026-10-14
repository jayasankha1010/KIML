"""
Check the collected per-gene predictions against the manuscript's Table 1.

collect_paper_predictions.py re-averages each experiment's fold files using a
delimiter-anchored prefix, excluding sibling experiments that the original
summarizer swept in (it matched on a bare startswith). This script recomputes
the median rank from those clean averages and compares it with the published
value.

  match    the original summarisation was unaffected - sibling experiments
           presumably did not exist yet when it was run. Nothing to do.
  differ   that cell of Table 1 was computed over a blended file set and the
           published number is wrong.

The median-rank calculation here is a line-for-line copy of the one in
results_processing/evaluate_results.py, so any difference is attributable to the
input file set rather than to the metric.

Usage (locally, after copying paper_predictions/ back from Spartan):

    python additional_experiments/revision_runs/verify_paper_predictions.py
"""

import argparse
import csv
import os

import pandas as pd

# Same mapping evaluate_results.py uses, disease -> post-split target list.
DISEASE_TARGETS = {
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


def median_rank_unseen(predictions_path, targets_path):
    """Replicates evaluate_results.calculate_ranks(), median-rank portion only."""
    df = pd.read_csv(predictions_path, sep="\t")
    df = df.sort_values(by="avg_probability", ascending=False)

    df_unseen = df[df["truth"] != 1].copy()
    df_unseen["rank"] = df_unseen["avg_probability"].rank(
        ascending=False, method="first").astype(int)

    with open(targets_path) as handle:
        targets = {line.strip() for line in handle if line.strip()}

    df_unseen["new_status"] = df_unseen["hgnc"].isin(targets)
    ranks = df_unseen.loc[df_unseen["new_status"], "rank"]
    return ranks.median(), int(ranks.shape[0]), len(df_unseen)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lookup", default=os.path.join(here, "experiment_lookup.tsv"))
    parser.add_argument("--predictions", default=os.path.join(here, "paper_predictions"))
    parser.add_argument("--disease-dir",
                        default=os.path.join(root, "data", "kiml_data", "diseases"))
    parser.add_argument("--tolerance", type=float, default=1.0,
                        help="allowed absolute difference before flagging (default 1.0)")
    args = parser.parse_args()

    with open(args.lookup) as handle:
        lookup = list(csv.DictReader(handle, delimiter="\t"))

    print("{:26}{:9}{:>9}{:>11}{:>12}{:>9}  status".format(
        "disease", "variant", "exp", "Table 1", "recomputed", "targets"))
    print("-" * 88)

    agree = differ = skipped = 0
    mismatches = []
    for entry in lookup:
        experiment = entry["experiment_id"]
        disease = entry["disease"]
        predictions = os.path.join(args.predictions, "{}_probabilities.tsv".format(experiment))
        targets = os.path.join(args.disease_dir, DISEASE_TARGETS.get(disease, ""))

        if not os.path.exists(predictions):
            print("{:26}{:9}{:>9}{:>11}{:>12}{:>9}  MISSING FILE".format(
                disease, entry["paper_variant"], experiment,
                entry["table1_median"], "-", "-"))
            skipped += 1
            continue
        if not os.path.exists(targets):
            print("{:26}{:9}{:>9}  no target list".format(
                disease, entry["paper_variant"], experiment))
            skipped += 1
            continue

        published = float(entry["table1_median"])
        recomputed, n_targets, universe = median_rank_unseen(predictions, targets)

        if pd.isna(recomputed):
            status = "NO TARGETS FOUND"
            differ += 1
        elif abs(recomputed - published) <= args.tolerance:
            status = "ok"
            agree += 1
        else:
            status = "DIFFERS by {:+.1f}".format(recomputed - published)
            differ += 1
            mismatches.append((disease, entry["paper_variant"], experiment,
                               published, recomputed))

        print("{:26}{:9}{:>9}{:>11}{:>12}{:>9}  {}".format(
            disease, entry["paper_variant"], experiment,
            "{:g}".format(published),
            "-" if pd.isna(recomputed) else "{:g}".format(recomputed),
            n_targets, status))

    print("-" * 88)
    print("reproduced {}, differ {}, skipped {}".format(agree, differ, skipped))

    if mismatches:
        print("\n" + "=" * 72)
        print(" TABLE 1 CELLS THAT DO NOT REPRODUCE")
        print("=" * 72)
        for disease, variant, experiment, published, recomputed in mismatches:
            print("  {:24} {:8} {:8}  published {:>9g}  clean {:>9g}".format(
                disease, variant, experiment, published, recomputed))
        print("\n  These were summarised over a file set that included sibling")
        print("  experiments sharing a numeric prefix. The 'clean' column is the")
        print("  value from that experiment's own fold files alone. Table 1, the")
        print("  abstract and any text quoting these numbers need updating, and")
        print("  the corrected values should be used for every revision analysis.")
        print("=" * 72)
    elif agree and not differ:
        print("\nAll reproduced. The prefix collision did not affect the published")
        print("numbers - the colliding experiments post-date the summarisation.")


if __name__ == "__main__":
    main()
