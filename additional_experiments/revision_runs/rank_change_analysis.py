"""
Who moves when knowledge is added, and why? (Reviewer 1 comment 13, Reviewer 4)

R1.13: "The TSC2 example shows an interpretable subnetwork and demonstrates how
knowledge and experimental information can contribute differently to one
prediction. However, this can be construed as selectively picking the evidence
to justify the means. Robustness should be quantified."

R4: "How about movement the other way? Are there known genes ranking high in the
data-only method but rank low when prior knowledge is added by this
methodology? What then is the explanation - when prior knowledge contradicts the
data (or integration of it makes prediction worse)?"

The manuscript rests this section on a single gene (TSC2, 1153 -> 10). One
example cannot distinguish a real mechanism from a favourable anecdote, and
Reviewer 4 - the accept vote - asked specifically for the opposite direction.

This replaces the anecdote with the full distribution of rank changes from the
experimental-only model to the knowledge-inclusive one, over every post-split
target gene, and selects examples by a FIXED RULE rather than by hand: the
largest gains and the largest losses. Both directions are reported.

It also reports, for each mover, how many pre-cutoff papers mentioned the
disease (from extract_pubmed_counts.py). That is the natural explanation to
test for R4's question: genes that fall when knowledge is added should be ones
where the literature carried no disease signal, so the knowledge features add
noise rather than evidence.

Usage:
    python additional_experiments/revision_runs/rank_change_analysis.py
"""

import argparse
import csv
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from revision_analysis import ARMS, DISEASE_TARGETS, load_predictions, rank_unseen  # noqa: E402

N_EXAMPLES = 5


def read_genes(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def load_evidence(path, disease):
    column = disease + "_evidence"
    counts = {}
    if not os.path.exists(path):
        return counts
    with open(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if column not in (reader.fieldnames or []):
            return counts
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
    parser.add_argument("--disease-dir",
                        default=os.path.join(ROOT, "data", "kiml_data", "diseases"))
    parser.add_argument("--mantis-lookup", default=os.path.join(HERE, "mantis_lookup.tsv"))
    parser.add_argument("--mantis-predictions",
                        default=os.path.join(ROOT, "external", "Mantis", "mantis_results"))
    parser.add_argument("--counts",
                        default=os.path.join(ROOT, "additional_experiments", "popularity",
                                             "pubmed_counts_2022_09.tsv"))
    parser.add_argument("-o", "--out", default=os.path.join(HERE, "rank_changes.tsv"))
    args = parser.parse_args()

    by_disease = {}
    with open(args.lookup) as handle:
        for entry in csv.DictReader(handle, delimiter="\t"):
            path = os.path.join(args.predictions,
                                "{}_probabilities.tsv".format(entry["experiment_id"]))
            by_disease.setdefault(entry["disease"], {})[entry["paper_variant"]] = path

    # The RF arm lives in a separate lookup and directory; without it this
    # analysis silently covers only half the manuscript.
    if os.path.exists(args.mantis_lookup):
        with open(args.mantis_lookup) as handle:
            for entry in csv.DictReader(handle, delimiter="\t"):
                path = os.path.join(args.mantis_predictions, entry["predictions_file"])
                by_disease.setdefault(entry["disease"], {})[entry["paper_variant"]] = path

    summary, movers = [], []
    print("{:24}{:10}{:>8}{:>9}{:>9}{:>9}{:>10}{:>9}".format(
        "disease", "arm", "n", "improved", "worsened", "median", "mean", "|>1000|"))
    print("-" * 90)

    for disease, variants in sorted(by_disease.items()):
        target_file = DISEASE_TARGETS.get(disease)
        if not target_file:
            continue
        target_path = os.path.join(args.disease_dir, target_file)
        if not os.path.exists(target_path):
            continue
        targets = read_genes(target_path)
        evidence = load_evidence(args.counts, disease)

        for arm_name, arm in ARMS.items():
            before_path = variants.get(arm["experimental"])
            after_path = variants.get(arm["combined"])
            if not before_path or not after_path:
                continue
            if not (os.path.exists(before_path) and os.path.exists(after_path)):
                continue

            before, _ = rank_unseen(load_predictions(before_path))
            after, _ = rank_unseen(load_predictions(after_path))

            shared = sorted(set(before) & set(after) & targets)
            if len(shared) < 5:
                continue

            # Negative change = the gene moved UP when knowledge was added.
            changes = {gene: after[gene] - before[gene] for gene in shared}
            values = sorted(changes.values())
            improved = sum(1 for v in values if v < 0)
            worsened = sum(1 for v in values if v > 0)
            big = sum(1 for v in values if abs(v) > 1000)

            summary.append({
                "disease": disease, "arm": arm_name, "n_targets": len(values),
                "n_improved": improved, "n_worsened": worsened,
                "pct_improved": round(100.0 * improved / len(values), 1),
                "median_change": statistics.median(values),
                "mean_change": round(statistics.mean(values), 1),
                "n_moved_over_1000": big,
            })
            print("{:24}{:10}{:>8}{:>9}{:>9}{:>9.0f}{:>10.0f}{:>9}".format(
                disease, arm_name, len(values), improved, worsened,
                statistics.median(values), statistics.mean(values), big))

            # Fixed-rule examples: biggest gains and biggest losses. No hand
            # selection, so the section cannot be read as cherry-picked.
            ordered = sorted(changes.items(), key=lambda item: item[1])
            for direction, picks in (("gain", ordered[:N_EXAMPLES]),
                                     ("loss", ordered[-N_EXAMPLES:])):
                for gene, change in picks:
                    movers.append({
                        "disease": disease, "arm": arm_name, "direction": direction,
                        "gene": gene,
                        "rank_experimental_only": before[gene],
                        "rank_knowledge_inclusive": after[gene],
                        "change": change,
                        "pre_cutoff_disease_papers": evidence.get(gene, ""),
                    })

    for name, payload in [("", summary), ("_movers", movers)]:
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

    # Does prior disease literature explain which genes fall? This is the
    # direct test of Reviewer 4's question.
    gains = [m for m in movers if m["direction"] == "gain"
             and isinstance(m["pre_cutoff_disease_papers"], int)]
    losses = [m for m in movers if m["direction"] == "loss"
              and isinstance(m["pre_cutoff_disease_papers"], int)]
    if gains and losses:
        g = statistics.median(m["pre_cutoff_disease_papers"] for m in gains)
        l = statistics.median(m["pre_cutoff_disease_papers"] for m in losses)
        print("\n" + "=" * 78)
        print(" WHY DO SOME GENES FALL? (Reviewer 4's question)")
        print("=" * 78)
        print("  median pre-cutoff disease papers, biggest GAINS : {:g}  (n={})".format(g, len(gains)))
        print("  median pre-cutoff disease papers, biggest LOSSES: {:g}  (n={})".format(l, len(losses)))
        if g > l:
            print("\n  Genes that rise have more prior disease literature than those that")
            print("  fall, so the knowledge features are adding evidence where evidence")
            print("  exists and diluting the experimental signal where it does not.")
        else:
            print("\n  Prior disease literature does NOT separate risers from fallers, so")
            print("  the movement has some other cause - worth checking network degree")
            print("  or expression coverage before offering an explanation.")
        print("=" * 78)


if __name__ == "__main__":
    main()
