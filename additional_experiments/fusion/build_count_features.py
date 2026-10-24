"""
Publication count as a NODE FEATURE (Reviewer 1, comment 5 iii).

R1.5 asks for an ablation separating "literature-semantic information versus
simple PubMed article-count/popularity signals". The popularity baseline in
additional_experiments/popularity answers that for a *ranking* - rank genes by
paper count and see how far that gets you. This answers the different and
sharper question: given the same model and graph, how much of the gain do you
keep if the literature enters as a COUNT rather than as semantics?

Three dimensions, all from the pre-cutoff counts:
    raw        papers before 2022-10-01
    log1p      the same, compressed - counts are heavily skewed
    percentile rank-normalised to [0, 1], scale-free

Written in the same whitespace-separated "gene v1 v2 ..." layout as every other
feature matrix, so it drops into the same loaders.

Usage:
    python additional_experiments/fusion/build_count_features.py
"""

import argparse
import csv
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

COUNTS = os.path.join(ROOT, "additional_experiments", "popularity",
                      "pubmed_counts_2022_09.tsv")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--counts", default=COUNTS)
    parser.add_argument("--column", default="n_papers_pre_cutoff")
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "pubmed_count_3d_2022_09.txt"))
    args = parser.parse_args()

    counts = {}
    with open(args.counts) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            try:
                counts[row["gene"].strip()] = int(row[args.column])
            except (TypeError, ValueError, KeyError):
                continue
    if not counts:
        raise SystemExit("No counts read from {}".format(args.counts))

    # Percentile over the observed distribution, so the feature is comparable
    # across diseases and unaffected by the long tail.
    ordered = sorted(counts.values())
    n = len(ordered)
    import bisect
    def percentile(value):
        return bisect.bisect_right(ordered, value) / n

    with open(args.out, "w") as handle:
        for gene in sorted(counts):
            c = counts[gene]
            handle.write("{} {:.6f} {:.6f} {:.6f}\n".format(
                gene, float(c), math.log1p(c), percentile(c)))

    values = sorted(counts.values())
    print("Wrote {}".format(args.out))
    print("  {} genes x 3 dims".format(len(counts)))
    print("  counts: min {}, median {}, max {}".format(
        values[0], values[n // 2], values[-1]))
    print("\nNext: align to the SPEOS gene namespace, which uses deprecated symbols:")
    print("  python additional_experiments/text_representations/align_to_speos_symbols.py \\")
    print("      --matrix {}".format(args.out))


if __name__ == "__main__":
    main()
