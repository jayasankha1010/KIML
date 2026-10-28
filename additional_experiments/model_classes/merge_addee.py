"""
Fold the AD/AR DEE results into the main model-class tables.

R1.3 and R1.4 originally covered seven diseases while Table 1 covers nine -
AD DEE and AR DEE were missing from the DISEASES dict in run_model_classes.py.
They were run separately into *_addee.tsv rather than recomputing the seven
that were already done, so those need merging back.

Idempotent: rows are keyed on (disease, model, features), so re-running
replaces rather than duplicates. That matters because a duplicated row would
quietly skew every count computed from these files - "25 of 35 combinations"
and the like.

Usage:
    python additional_experiments/model_classes/merge_addee.py
    python additional_experiments/model_classes/merge_addee.py --dry-run
"""

import argparse
import csv
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

PAIRS = [
    ("model_class_metrics.tsv", "model_class_metrics_addee.tsv"),
    ("model_class_tfidf_full.tsv", "model_class_tfidf_full_addee.tsv"),
    ("model_class_tfidf_title.tsv", "model_class_tfidf_title_addee.tsv"),
    ("model_class_doc2vec.tsv", "model_class_doc2vec_addee.tsv"),
]
KEY = ("disease", "model", "features")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for base_name, add_name in PAIRS:
        base_path = os.path.join(HERE, base_name)
        add_path = os.path.join(HERE, add_name)
        if not os.path.exists(add_path):
            print("[skip] no {}".format(add_name))
            continue
        if not os.path.exists(base_path):
            print("[skip] no {}".format(base_name))
            continue

        with open(base_path) as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            columns = list(reader.fieldnames)
            rows = list(reader)
        with open(add_path) as handle:
            add_reader = csv.DictReader(handle, delimiter="\t")
            add_columns = list(add_reader.fieldnames)
            add_rows = list(add_reader)

        if columns != add_columns:
            print("[Error] {}: column mismatch, refusing to merge".format(base_name))
            print("        base has {}, add has {}".format(
                len(columns), len(add_columns)))
            continue

        merged = {tuple(r[k] for k in KEY): r for r in rows}
        replaced = sum(1 for r in add_rows if tuple(r[k] for k in KEY) in merged)
        for r in add_rows:
            merged[tuple(r[k] for k in KEY)] = r
        out = sorted(merged.values(), key=lambda r: (r["disease"], r["model"],
                                                     r["features"]))

        diseases = sorted({r["disease"] for r in out})
        print("{:34} {:3} -> {:3} rows   {} diseases{}".format(
            base_name, len(rows), len(out), len(diseases),
            "   ({} replaced)".format(replaced) if replaced else ""))

        if args.dry_run:
            continue
        shutil.copy(base_path, base_path + ".bak")
        with open(base_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
            writer.writeheader()
            writer.writerows(out)

    if args.dry_run:
        print("\n(dry run - nothing written)")
    else:
        print("\nMerged. Backups written alongside as *.tsv.bak")


if __name__ == "__main__":
    main()
