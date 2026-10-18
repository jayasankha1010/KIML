"""
Does KIML still work on genes with no prior disease literature? (Reviewer 1, comment 7)

R1.7: "The manuscript treats genes added to Genes4Epilepsy or PanelApp after
September 2022 as genes 'discovered' after the cutoff. A gene added to a panel
in 2024 may already have had substantial disease-related literature before
September 2022. The authors need to distinguish first evidence of the gene-
disease relationship from the date of database curation. Otherwise, this
experiment may partly measure prediction of subsequent panel inclusion rather
than genuine feature discovery."

This is the most dangerous comment in the set, because it questions whether the
temporal split measures discovery at all. Counting how many target genes had
prior literature (405 of 1033, 39%) describes the problem but does not answer
it. The answer is to re-run every metric separately on the two strata:

    NOVEL          no pre-cutoff paper mentions the disease  (n = 628)
    PRIOR EVIDENCE at least one such paper                   (n = 405)

If the advantage holds on the NOVEL stratum, the comment is answered on the
reviewer's own terms: those genes cannot be cases of the model recognising
literature that already linked them to the disease, so performance there is
genuine prediction rather than curation lag.

Because keyword matching favours recall, the prior-evidence set is an upper
bound and the NOVEL stratum is correspondingly conservative - which is the
direction that helps this argument.

Prior-evidence counts come from extract_pubmed_counts.py (<disease>_evidence
columns). Metrics and the paired bootstrap are imported from revision_analysis
so the definitions cannot drift.

Usage:
    python additional_experiments/revision_runs/stratify_prior_literature.py
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from revision_analysis import (  # noqa: E402
    ARMS, DISEASE_TARGETS, bootstrap, load_predictions, paired_bootstrap, rank_unseen)

STRATA = ["novel", "prior evidence"]


def load_evidence(path, disease):
    """gene -> number of pre-cutoff papers mentioning this disease."""
    column = disease + "_evidence"
    counts = {}
    with open(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if column not in (reader.fieldnames or []):
            return None
        for row in reader:
            try:
                counts[row["gene"]] = int(row[column])
            except (TypeError, ValueError):
                continue
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lookup", default=os.path.join(HERE, "experiment_lookup.tsv"))
    parser.add_argument("--predictions", default=os.path.join(HERE, "paper_predictions"))
    parser.add_argument("--counts",
                        default=os.path.join(ROOT, "additional_experiments", "popularity",
                                             "pubmed_counts_2022_09.tsv"))
    parser.add_argument("--disease-dir",
                        default=os.path.join(ROOT, "data", "kiml_data", "diseases"))
    parser.add_argument("--threshold", type=int, default=1,
                        help="pre-cutoff disease papers needed to count as PRIOR EVIDENCE "
                             "(default 1). Raising it moves marginal genes into the NOVEL "
                             "stratum, so the conclusion should be checked for sensitivity "
                             "to this choice - a single keyword hit is weak evidence that a "
                             "gene was already linked to the disease.")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out", default=os.path.join(HERE, "r17_stratified.tsv"))
    args = parser.parse_args()

    if not os.path.exists(args.counts):
        sys.exit("Need {} - run extract_pubmed_counts.py on the cluster first.".format(
            args.counts))

    by_disease = {}
    with open(args.lookup) as handle:
        for entry in csv.DictReader(handle, delimiter="\t"):
            path = os.path.join(args.predictions,
                                "{}_probabilities.tsv".format(entry["experiment_id"]))
            by_disease.setdefault(entry["disease"], {})[entry["paper_variant"]] = path

    rows, contrasts = [], []
    print("{:24}{:16}{:10}{:>8}{:>10}  {}".format(
        "disease", "method", "stratum", "n", "median", "95% CI"))
    print("-" * 82)

    for disease, variants in by_disease.items():
        target_file = DISEASE_TARGETS.get(disease)
        if not target_file:
            continue
        target_path = os.path.join(args.disease_dir, target_file)
        if not os.path.exists(target_path):
            continue
        evidence = load_evidence(args.counts, disease)
        if evidence is None:
            print("  [skip] {}: no evidence column".format(disease))
            continue

        with open(target_path) as handle:
            targets = {line.strip() for line in handle if line.strip()}
        strata = {
            "novel": sorted(g for g in targets if evidence.get(g, 0) < args.threshold),
            "prior evidence": sorted(g for g in targets if evidence.get(g, 0) >= args.threshold),
        }

        ranked = {}
        for method, path in variants.items():
            if not os.path.exists(path):
                continue
            rank_of, universe = rank_unseen(load_predictions(path))
            ranked[method] = (rank_of, universe)

            for stratum in STRATA:
                hit_ranks = [rank_of[g] for g in strata[stratum] if g in rank_of]
                if not hit_ranks:
                    continue
                point, bounds = bootstrap(hit_ranks, universe, args.n_boot, args.seed)
                record = {"disease": disease, "method": method, "stratum": stratum,
                          "n_targets": len(hit_ranks), "universe_size": universe}
                for key, value in point.items():
                    record[key] = round(value, 4)
                    if key in bounds:
                        record[key + "_lo"] = round(bounds[key][0], 4)
                        record[key + "_hi"] = round(bounds[key][1], 4)
                rows.append(record)
                ci = bounds.get("median_rank_unseen")
                print("{:24}{:16}{:10}{:>8}{:>10}  {}".format(
                    disease, method, stratum, len(hit_ranks),
                    "{:g}".format(point["median_rank_unseen"]),
                    "[{:g}, {:g}]".format(*ci) if ci else "-"))

        # The actual test: within each stratum, does KIML still beat its
        # experimental-only baseline on the same genes?
        for arm in ARMS.values():
            a, b = arm["combined"], arm["experimental"]
            if a not in ranked or b not in ranked:
                continue
            for stratum in STRATA:
                genes = [g for g in strata[stratum] if g in ranked[a][0] and g in ranked[b][0]]
                if len(genes) < 5:
                    continue
                ranks_a = {g: ranked[a][0][g] for g in genes}
                ranks_b = {g: ranked[b][0][g] for g in genes}
                diffs, n_paired = paired_bootstrap(
                    ranks_a, ranks_b, ranked[a][1], ranked[b][1], args.n_boot, args.seed)
                if not diffs:
                    continue
                record = {"disease": disease, "contrast": "{} - {}".format(a, b),
                          "stratum": stratum, "n_paired_targets": n_paired}
                for key, (difference, lo, hi, significant) in diffs.items():
                    record[key] = round(difference, 4)
                    record[key + "_lo"] = round(lo, 4)
                    record[key + "_hi"] = round(hi, 4)
                    record[key + "_sig"] = "yes" if significant else "no"
                contrasts.append(record)

    if contrasts:
        print("\n" + "=" * 92)
        print(" DOES THE ADVANTAGE SURVIVE ON GENES WITH NO PRIOR DISEASE LITERATURE?")
        print(" negative favours the knowledge-inclusive model")
        print("=" * 92)
        print("{:24}{:20}{:16}{:>7}{:>11}  {:22}{}".format(
            "disease", "contrast", "stratum", "n", "difference", "95% CI", "sig"))
        for record in contrasts:
            key = "median_rank_unseen"
            if key not in record:
                continue
            print("{:24}{:20}{:16}{:>7}{:>11}  {:22}{}".format(
                record["disease"], record["contrast"], record["stratum"],
                record["n_paired_targets"], "{:+g}".format(record[key]),
                "[{:+g}, {:+g}]".format(record[key + "_lo"], record[key + "_hi"]),
                record[key + "_sig"]))
        print("=" * 92)

    for name, payload in [("", rows), ("_contrasts", contrasts)]:
        if not payload:
            continue
        columns = []
        for record in payload:
            for key in record:
                if key not in columns:
                    columns.append(key)
        path = args.out.replace(".tsv", name + ".tsv")
        with open(path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
            writer.writeheader()
            writer.writerows(payload)
        print("Wrote {} rows -> {}".format(len(payload), path))


if __name__ == "__main__":
    main()
