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


def load_kiml():
    ranks, universe = {}, {}
    sources = [(LOOKUP, PREDICTIONS, "paper_variant", "probabilities_file"),
               (MANTIS_LOOKUP, MANTIS_PREDICTIONS, "paper_variant", "predictions_file")]
    wanted = {a for _, a in EXISTING if a} | {a for _, a in OURS}
    for lookup, folder, variant_col, file_col in sources:
        if not os.path.exists(lookup):
            continue
        with open(lookup) as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row[variant_col] not in wanted:
                    continue
                path = os.path.join(folder, os.path.basename(row[file_col]))
                if not os.path.exists(path):
                    continue
                r, n = rank_unseen(load_predictions(path))
                ranks.setdefault(row["disease"], {})[row[variant_col]] = r
                universe.setdefault(row["disease"], {})[row[variant_col]] = n
    return ranks, universe


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "benchmark_existing_methods.tsv"))
    args = parser.parse_args()

    kiml, kiml_universe = load_kiml()
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
