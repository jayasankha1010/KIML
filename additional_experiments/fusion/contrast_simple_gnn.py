"""
Paired contrasts over the minimal-GNN ablation table (Reviewer 1, comment 5).

Every configuration ranks the SAME post-cutoff target genes, so comparing their
marginal confidence intervals is the wrong test and badly under-powered - the
shared difficulty of the target set inflates both intervals at once. These are
paired: resample genes, take the difference, bootstrap that.

Negative difference means the first configuration ranks targets higher (better).

Usage:
    python additional_experiments/fusion/merge_and_contrast.py
"""

import argparse
import csv
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "additional_experiments", "revision_runs"))
from revision_analysis import paired_bootstrap  # noqa: E402

# (label, configuration A, configuration B, which sub-ablation it answers)
CONTRASTS = [
    ("knowledge inclusion helps", "3_ll+hl_kg_concat", "1_ll_kg", "anchor"),
    ("literature beats expression", "2_hl_kg", "1_ll_kg", "anchor"),
    ("combined beats literature alone", "3_ll+hl_kg_concat", "2_hl_kg", "anchor"),
    ("sum vs concatenation", "4_ll+hl_kg_sum", "3_ll+hl_kg_concat", "R1.5 iv"),
    ("gated vs concatenation", "5_ll+hl_kg_gated", "3_ll+hl_kg_concat", "R1.5 iv"),
    ("message passing removed", "6_ll+hl_nograph", "3_ll+hl_kg_concat", "R1.5 v"),
    ("graph only (random features)", "7_random_kg", "3_ll+hl_kg_concat", "R1.5 ii"),
    ("graph only vs features only", "7_random_kg", "6_ll+hl_nograph", "R1.5 ii"),
    ("count instead of semantics", "8_ll+count_kg", "3_ll+hl_kg_concat", "R1.5 iii"),
    ("count alone vs semantics alone", "9_count_kg", "2_hl_kg", "R1.5 iii"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ranks", nargs="*",
                        default=sorted(glob.glob(os.path.join(HERE, "ranks_*.tsv"))))
    parser.add_argument("--metrics", nargs="*",
                        default=sorted(glob.glob(os.path.join(HERE, "metrics_*.tsv"))))
    parser.add_argument("--disease", default="dee",
                        help="which disease's rows to contrast; configuration "
                             "names repeat across diseases, so mixing them "
                             "would silently compare unrelated runs")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out", default=None)
    parser.add_argument("--merged-metrics", default=None)
    args = parser.parse_args()

    # Keep each disease in its own output rather than appending, so a second
    # disease cannot quietly overwrite the first one's table.
    if args.out is None:
        args.out = os.path.join(
            HERE, "simple_gnn_contrasts_{}.tsv".format(args.disease))
    if args.merged_metrics is None:
        args.merged_metrics = os.path.join(
            HERE, "simple_gnn_metrics_{}.tsv".format(args.disease))

    ranks, universe = {}, {}
    for path in args.ranks:
        with open(path) as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if "disease" not in row:
                    raise SystemExit(
                        "{} has no disease column; regenerate it with "
                        "run_simple_gnn.py --ranks-out".format(path))
                if row["disease"] != args.disease:
                    continue
                cfg = row["configuration"]
                ranks.setdefault(cfg, {})[row["gene"]] = int(row["rank"])
                universe[cfg] = int(row["universe_size"])
    if not ranks:
        raise SystemExit(
            "No rows for disease '{}' in {}".format(args.disease, args.ranks))

    # Merge the batched metric files into the single table for the paper.
    merged, columns = [], []
    for path in args.metrics:
        with open(path) as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row.get("disease") != args.disease:
                    continue
                merged.append(row)
                for key in row:
                    if key not in columns:
                        columns.append(key)
    merged.sort(key=lambda r: r["configuration"])
    with open(args.merged_metrics, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(merged)

    print("{:34}{:>10}{:>10}{:>22}{:>7}  {}".format(
        "contrast", "A", "B", "difference [95% CI]", "sig", "answers"))
    print("-" * 104)

    results = []
    for label, a, b, answers in CONTRASTS:
        if a not in ranks or b not in ranks:
            print("{:34}  (missing {})".format(
                label, a if a not in ranks else b))
            continue
        out, n = paired_bootstrap(ranks[a], ranks[b], universe[a], universe[b],
                                  args.n_boot, args.seed)
        diff, lo, hi, sig = out["median_rank_unseen"]
        med_a = sorted(ranks[a].values())[len(ranks[a]) // 2]
        med_b = sorted(ranks[b].values())[len(ranks[b]) // 2]
        print("{:34}{:>10}{:>10}{:>22}{:>7}  {}".format(
            label, med_a, med_b,
            "{:+.0f} [{:+.0f}, {:+.0f}]".format(diff, lo, hi),
            "yes" if sig else "no", answers))

        record = {"contrast": label, "A": a, "B": b, "answers": answers,
                  "n_shared_targets": n}
        for key, (d, l, h, s) in out.items():
            record[key] = round(d, 4)
            record[key + "_lo"] = round(l, 4)
            record[key + "_hi"] = round(h, 4)
            record[key + "_significant"] = s
        results.append(record)

    cols = []
    for record in results:
        for key in record:
            if key not in cols:
                cols.append(key)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    print("\nWrote {} contrasts -> {}".format(len(results), args.out))
    print("Merged {} rows -> {}".format(len(merged), args.merged_metrics))


if __name__ == "__main__":
    main()
