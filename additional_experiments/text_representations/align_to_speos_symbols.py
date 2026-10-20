"""
Align a feature matrix to the gene symbols SPEOS actually uses.

The published MiniLM embeddings use an older HGNC nomenclature - AARS, ABP1,
ACN9 - and the SPEOS universe matches them exactly, 17,282 of 17,282. The
TF-IDF matrices built from gene_details_2022_09.csv use current symbols -
AARS1, AOC1, SDHAF3 - because the ToppGene scrape was keyed on the current
HGNC list.

Feeding the TF-IDF matrix to SPEOS unaltered would silently drop 2,029 genes
from the graph, because the preprocessor removes any node whose features are
missing. The classical arm would then be scored on a smaller universe than
MiniLM, which rigs the comparison in MiniLM's favour - precisely the bias
Reviewer 1 comment 4 is testing for.

This renames rows using HGNC previous/alias symbols so the matrix is keyed the
way SPEOS expects, and emits an all-zero row for any gene still unmatched so
the universe is preserved exactly. Zero rows are reported, not hidden: they are
a real handicap for the classical arm and need to be stated when the comparison
is reported.

Usage:
    python additional_experiments/text_representations/align_to_speos_symbols.py \
        --matrix additional_experiments/text_representations/pubmed_tfidf_svd_full_384d_2022_09.txt
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

REFERENCE = os.path.join(ROOT, "data", "kiml_data", "pubmed_embeddings",
                         "pubmed_embeddings_rearranged_2022_09.txt")
HGNC = os.path.join(ROOT, "external", "SPEOS", "hgnc", "hgnc_official_list.tsv")


def load_symbol_map(path):
    """current symbol -> {previous and alias symbols}."""
    mapping = {}
    with open(path) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            current = (row.get("symbol") or "").strip()
            if not current:
                continue
            olds = set()
            for field in ("prev_symbol", "alias_symbol"):
                raw = (row.get(field) or "").replace('"', "")
                olds.update(s.strip() for s in raw.split("|") if s.strip())
            if olds:
                mapping[current] = olds
    return mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--reference", default=REFERENCE,
                        help="file whose gene symbols define the target namespace")
    parser.add_argument("--hgnc", default=HGNC)
    parser.add_argument("--targets-dir",
                        default=os.path.join(ROOT, "data", "kiml_data", "diseases"))
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()

    wanted = [line.split()[0] for line in open(args.reference) if line.strip()]
    wanted_set = set(wanted)
    print("Reference namespace: {} genes".format(len(wanted)))

    rows = {}
    dims = None
    with open(args.matrix) as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2:
                continue
            rows[parts[0]] = parts[1:]
            dims = dims or len(parts) - 1
    print("Input matrix       : {} genes x {} dims".format(len(rows), dims))

    # current -> old, so a row keyed on the current symbol can be re-keyed to
    # whichever old symbol the reference namespace uses.
    current_to_old = load_symbol_map(args.hgnc)
    alias_rows = {}
    for current, olds in current_to_old.items():
        if current not in rows:
            continue
        for old in olds:
            if old in wanted_set and old not in rows:
                alias_rows.setdefault(old, rows[current])

    direct = sum(1 for g in wanted if g in rows)
    renamed = sum(1 for g in wanted if g not in rows and g in alias_rows)
    zeros = len(wanted) - direct - renamed
    print("\nCoverage of the reference namespace:")
    print("  matched directly          {:>6}".format(direct))
    print("  matched via prev/alias    {:>6}".format(renamed))
    print("  no text, zero-filled      {:>6}  ({:.1f}%)".format(
        zeros, 100.0 * zeros / len(wanted)))

    # Do the zero-filled genes actually appear as post-split targets? If not,
    # the handicap is cosmetic; if so, it has to be stated.
    unmatched = [g for g in wanted if g not in rows and g not in alias_rows]
    if unmatched and os.path.isdir(args.targets_dir):
        unmatched_set = set(unmatched)
        print("\n  zero-filled genes appearing as post-split targets:")
        total_hit = 0
        for name in sorted(os.listdir(args.targets_dir)):
            if "_vs_" not in name and "_to_" not in name:
                continue
            with open(os.path.join(args.targets_dir, name)) as handle:
                targets = {l.strip() for l in handle if l.strip()}
            hit = targets & unmatched_set
            total_hit += len(hit)
            if hit:
                print("    {:52} {:>3} of {:>4}".format(name, len(hit), len(targets)))
        if total_hit == 0:
            print("    none - the zero rows never appear in any target list, so they")
            print("    cannot affect the reported metrics")

    out = args.out or args.matrix.replace(".txt", "_speos_symbols.txt")
    zero_vector = ["0.000000"] * dims
    with open(out, "w") as handle:
        for gene in wanted:
            vector = rows.get(gene) or alias_rows.get(gene) or zero_vector
            handle.write(gene + " " + " ".join(vector) + "\n")
    print("\nWrote {} ({} genes x {} dims, keyed as SPEOS expects)".format(
        out, len(wanted), dims))
    return 0


if __name__ == "__main__":
    sys.exit(main())
