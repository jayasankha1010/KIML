"""
Audit the Summary sheet of Supp_Data_2.xlsx against its own source sheets.

The Summary sheet is hand-assembled from Mantis_rank_metrics (the RF arm) and
speos_rank_metrics (the GNN arm). Hand-assembly is where the "Fold Enrichment
1%" block went wrong: its RF columns were taken from fold_enrichment_top_5_pct
instead of fold_enrichment_top_1_pct, in every single cell, so the table
compares RF at 5% against GNN at 1%.

This re-derives every RF cell from the source rows and reports mismatches,
flagging the specific case where a cell matches the neighbouring 5% column -
that signature is what identifies a column shift rather than a typo.

Usage:
    python additional_experiments/supp_fixes/check_supp_data_2.py
    python additional_experiments/supp_fixes/check_supp_data_2.py --write-correction
"""

import argparse
import csv
import os

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORKBOOK = os.path.join(ROOT, "rebuttal", "Supp_Data_2.xlsx")

# Column offsets in Mantis_rank_metrics. The sheet's header row sits at the
# bottom; these follow it.
MANTIS = {"median": 4, "fe1": 8, "fe5": 10, "prec100": 20, "rec100": 21}
# ... and in speos_rank_metrics, which has an extra 'compare_from' column.
SPEOS = {"median": 3, "fe1": 9, "fe5": 11, "prec100": 21, "rec100": 22}

# Summary sheet: first RF column of each block. RF occupies +0..+2 (LL, HL,
# LL+HL) and GNN +3..+5. The disease label sits one column to the left.
BLOCKS = [("median rank", 2, "median", None),
          ("FE@1%", 11, "fe1", "fe5"),
          ("precision@100", 20, "prec100", None),
          ("recall@100", 29, "rec100", None)]

# Summary label -> (Mantis LL row, Mantis HL row, Mantis LL+HL row), speos tag.
DISEASES = {
    "DEE": (("DEE (Original)", "DEE (only PubMed)", "DEE (+PubMed)"), "dee"),
    "AD DEE": (("AD DEE (2022)", "AD DEE (only PubMed)", "AD DEE (+PubMed)"), "ad_dee"),
    "AR DEE": (("AR DEE (2022)", "AR DEE (only PubMed)", "AR DEE (+PubMed)"), "ar_dee"),
    "Microcephaly": (("Microcephaly", "Microcephaly (only PubMed)",
                      "Microcephaly (+PubMed)"), "microcephaly"),
    "Intellectual Disability": (("Intellectual Disability",
                                 "Intellectual Disability (only PubMed)",
                                 "Intellectual Disability (+PubMed)"),
                                "intellectual_disability"),
    "Motor Neuron Disease": (("MND", "MND (only PubMed)", "MND (+PubMed)"), "mnd"),
    "Cerebral Palsy": (("CP", "CP (only PubMed)", "CP (+PubMed)"), "cp"),
    "Bleeding  and Platelet Disorder": (("Platelet Disorder (only LL)",
                                         "Platelet Disorder (only PubMed)",
                                         "Platelet Disorder (HL+LL)"),
                                        "platelet_disorder"),
    "Arthrogryposis": (("Arthrogryposis", "Arthogryposis",
                        "Arthrogryposis (+PubMed)"), "arthrogryposis"),
}
ARMS = ["LL", "HL", "LL+HL"]
SPEOS_ARM = {"LL": "ll_only", "HL": "hl_only", "LL+HL": "hl_ll"}


def close(a, b, tol=1e-3):
    return a is not None and b is not None and abs(float(a) - float(b)) < tol


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workbook", default=WORKBOOK)
    parser.add_argument("--write-correction", action="store_true",
                        help="emit fe1_correction.tsv with published vs corrected values")
    args = parser.parse_args()

    book = openpyxl.load_workbook(args.workbook, data_only=True)

    mantis = {}
    for row in book["Mantis_rank_metrics"].iter_rows(values_only=True):
        if row[0] and row[1] in ("LL", "HL", "LL_HL"):
            mantis[row[0]] = {k: row[i] for k, i in MANTIS.items()}
    speos = {}
    for row in book["speos_rank_metrics"].iter_rows(values_only=True):
        if row[0] in ("ll_only", "hl_only", "hl_ll"):
            speos[(row[0], row[1])] = {k: row[i] for k, i in SPEOS.items()}

    summary = list(book["Summary"].iter_rows(values_only=True))
    problems = []

    for name, col, key, alt in BLOCKS:
        correct = wrong = shifted = 0
        seen = set()
        for row in summary:
            label = row[col - 1] if col - 1 < len(row) else None
            if label not in DISEASES:
                continue
            names, _ = DISEASES[label]
            for j, arm in enumerate(ARMS):
                value = row[col + j] if col + j < len(row) else None
                source = mantis.get(names[j])
                if value is None or not source or source[key] is None:
                    continue
                if close(value, source[key]):
                    correct += 1
                    continue
                wrong += 1
                if alt and close(value, source[alt]):
                    shifted += 1
                if (label, arm) not in seen:
                    seen.add((label, arm))
                    problems.append((name, label, arm, value, source[key],
                                     source[alt] if alt else None))
        note = "  <-- all match {}, i.e. a column shift".format(alt) if shifted and shifted == wrong else ""
        print("{:16} RF cells correct: {:3}   wrong: {:3}{}".format(
            name, correct, wrong, note))

    if problems:
        print("\nDistinct mismatched cells:")
        print("  {:16}{:32}{:8}{:>12}{:>12}{:>12}".format(
            "block", "disease", "arm", "published", "expected", "5% value"))
        for block, label, arm, value, expected, alt in problems:
            print("  {:16}{:32}{:8}{:>12}{:>12}{:>12}".format(
                block, label, arm, str(value), str(expected), str(alt)))

    if args.write_correction:
        out = os.path.join(HERE, "fe1_correction.tsv")
        rows = []
        for label, (names, tag) in DISEASES.items():
            published = next((r for r in summary
                              if len(r) > 11 and r[10] == label and r[11] is not None), None)
            for j, arm in enumerate(ARMS):
                rows.append({
                    "disease": label, "arm": arm,
                    "rf_published_fe1": published[11 + j] if published else None,
                    "rf_corrected_fe1": (mantis.get(names[j]) or {}).get("fe1"),
                    "gnn_fe1": (speos.get((SPEOS_ARM[arm], tag)) or {}).get("fe1"),
                })
        with open(out, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
        print("\nWrote {}".format(out))


if __name__ == "__main__":
    main()
