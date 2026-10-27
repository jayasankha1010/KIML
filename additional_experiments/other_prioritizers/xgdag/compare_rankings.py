"""
Does our XGDAG run reproduce the authors' published ranking?

This is the gate. Before adapting XGDAG to our diseases, we run it unmodified
on one of ITS OWN diseases and check the output against the ranking shipped in
the repository. If their published result does not reproduce, nothing built on
top of it can be trusted - the same reasoning as the anchor check that caught
the overfitting bug in the minimal GNN.

Exact agreement is not expected and not required. GNNExplainer is stochastic
and the training script is unseeded, so two runs differ. What matters is
whether the two rankings agree far more than chance.

Reported at several depths, because agreement that holds only at one cutoff is
an artefact:

  overlap@K   how many of the top K genes appear in both lists
  expected    what overlap@K would be if the two rankings were independent,
              i.e. K^2 / N - the number to beat
  ratio       observed / expected; 1.0 is chance, higher is agreement

Usage:
    python compare_rankings.py OURS.txt THEIRS.txt
"""

import argparse
import sys


def read_ranking(path):
    genes, seen = [], set()
    with open(path) as handle:
        for line in handle:
            gene = line.strip().split()[0] if line.strip() else ""
            if gene and gene not in seen:
                seen.add(gene)
                genes.append(gene)
    return genes


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ours")
    parser.add_argument("theirs")
    parser.add_argument("--depths", type=int, nargs="*",
                        default=[10, 50, 100, 250, 500, 1000])
    args = parser.parse_args()

    ours = read_ranking(args.ours)
    theirs = read_ranking(args.theirs)
    print("ours  : {:6} genes  {}".format(len(ours), args.ours))
    print("theirs: {:6} genes  {}".format(len(theirs), args.theirs))

    shared_universe = set(ours) & set(theirs)
    print("both rank the same gene: {} of {} / {}".format(
        len(shared_universe), len(ours), len(theirs)))
    if not shared_universe:
        print("\nNO SHARED GENES - the runs are not comparable. Check that the")
        print("same disease and method were used.")
        return 1

    # Chance baseline uses the shared universe: two independent rankings of N
    # genes share about K^2/N of their top K.
    n = len(shared_universe)
    print("\n{:>8}{:>12}{:>12}{:>10}".format("K", "overlap", "expected", "ratio"))
    print("-" * 44)
    ratios = []
    for k in args.depths:
        if k > min(len(ours), len(theirs)):
            continue
        top_a, top_b = set(ours[:k]), set(theirs[:k])
        overlap = len(top_a & top_b)
        expected = k * k / n
        ratio = overlap / expected if expected else float("nan")
        ratios.append(ratio)
        print("{:>8}{:>12}{:>12.1f}{:>10.1f}x".format(k, overlap, expected, ratio))

    # Rank correlation over the shared genes, as a whole-list check that does
    # not depend on choosing a cutoff.
    rank_a = {g: i for i, g in enumerate(ours)}
    rank_b = {g: i for i, g in enumerate(theirs)}
    common = sorted(shared_universe)
    m = len(common)
    if m > 2:
        a = [rank_a[g] for g in common]
        b = [rank_b[g] for g in common]
        mean_a, mean_b = sum(a) / m, sum(b) / m
        cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
        var_a = sum((x - mean_a) ** 2 for x in a) ** 0.5
        var_b = sum((y - mean_b) ** 2 for y in b) ** 0.5
        rho = cov / (var_a * var_b) if var_a and var_b else float("nan")
        print("\nrank correlation over {} shared genes: {:.3f}".format(m, rho))

    print()
    median_ratio = sorted(ratios)[len(ratios) // 2] if ratios else 0.0
    if median_ratio >= 3:
        print("GATE PASSES. Agreement is well above chance, so the pipeline")
        print("reproduces the published behaviour. Safe to adapt to our diseases.")
        return 0
    if median_ratio >= 1.5:
        print("MARGINAL. Agreement is above chance but weak. Check the run used")
        print("the same model and graph as the shipped ranking before relying")
        print("on it - and say so in the write-up if we proceed.")
        return 0
    print("GATE FAILS. Agreement is near chance. Do NOT adapt this to our")
    print("diseases yet - our numbers would be meaningless. Check the disease,")
    print("the method, and whether the patch pointed at the right model/graph.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
