"""
XGDAG vs XGDAG+PubMed vs XGDAG+random: the within-method ablation.

Three rankings from the same pipeline on the same disease, differing only in
the node features:

  baseline   six NeDBIT features                 dee_kiml_xgdag_<method>.txt
  pubmed     + 384 MiniLM literature dimensions  dee_kiml_pubmed_xgdag_<method>.txt
  random     + 384 dimensions of noise           dee_kiml_random_xgdag_<method>.txt

THE ARMS DO NOT RANK THE SAME GENES. XGDAG's ranking comes out of explanation
subgraphs, so each trained model reaches a different subset of BioGRID, and
each arm has its own universe. Two consequences, both handled here:

  1. Raw ranks are not comparable across arms, so every rank is put on a
     common 0-10,000 scale (percentile x 10,000) before the paired bootstrap.
     Median and fold-enrichment are then comparable; recall@k is not, and is
     left out.

  2. Coverage is itself an outcome. A model that reaches more targets is
     better for a user even at equal median rank. So the PENALISED variant -
     every target scored, unreached ones placed past the end of the list - is
     the headline: it is paired on all targets, identical across arms. The
     RANKABLE variant is paired on the targets every arm reached.

The comparisons that matter are pubmed - baseline (does literature help?) and
pubmed - random (is it content, or just a wider input?). random - baseline is
reported too: if noise alone moves the ranking, the gain is capacity.

MEAN AS WELL AS MEDIAN. When about half the targets are unreached, the
penalised median sits on the penalty value itself and its interval collapses
to a point. The mean percentile still moves with every target, so it is the
better-behaved headline for the penalised variant.

Usage:
    python compare_pubmed_arms.py --disease dee \
        --rankings /data/gpfs/projects/punim2353/chathura/tools/XGDAG/Rankings
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "additional_experiments", "revision_runs"))
sys.path.insert(0, HERE)
from revision_analysis import bootstrap, paired_bootstrap  # noqa: E402
from score_xgdag import read_genes, read_ranking  # noqa: E402

SCALE = 10000
ARMS = [("baseline", ""), ("pubmed", "_pubmed"), ("random", "_random")]
CONTRASTS = [("pubmed", "baseline"), ("random", "baseline"), ("pubmed", "random")]
# Further baseline runs (six features, different random initialisation), used
# if present. XGDAG is unseeded, so one baseline run is one draw; differences
# BETWEEN baseline runs are the noise floor an ablation contrast must clear.
REPLICATES = [("rep2", "_rep2"), ("rep3", "_rep3")]
# Rank-scale metrics only; recall@k and precision@k assume a shared universe.
RANK_KEYS = ("median_rank_unseen", "mean_rank_unseen")
KEYS = ["median_rank_unseen", "mean_rank_unseen", "fold_enrichment_top_1_pct",
        "fold_enrichment_top_5_pct", "fold_enrichment_top_10_pct"]


def scaled(ranking, targets, penalise):
    """target -> rank on the common 0-SCALE axis."""
    universe = len(ranking)
    missing = [g for g in targets if g not in ranking]
    size = universe + (len(missing) if penalise else 0)
    out = {g: SCALE * ranking[g] / size for g in targets if g in ranking}
    if penalise:
        for g in missing:
            out[g] = SCALE * (universe + 1) / size
    return out


def spearman(a, b):
    """Rank correlation over the genes both rankings contain (no scipy)."""
    shared = [g for g in a if g in b]
    if len(shared) < 3:
        return float("nan"), len(shared)

    def rerank(values):
        order = sorted(range(len(values)), key=values.__getitem__)
        ranks = [0] * len(values)
        for i, j in enumerate(order):
            ranks[j] = i + 1
        return ranks

    ra = rerank([a[g] for g in shared])
    rb = rerank([b[g] for g in shared])
    n = len(shared)
    d2 = sum((x - y) ** 2 for x, y in zip(ra, rb))
    return 1 - 6 * d2 / (n * (n * n - 1)), n


def top_overlap(a, b, k):
    top_a = {g for g, r in a.items() if r <= k}
    top_b = {g for g, r in b.items() if r <= k}
    return len(top_a & top_b)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disease", default="dee")
    parser.add_argument("--method", default="gnnexplainer")
    parser.add_argument("--rankings",
                        default="/data/gpfs/projects/punim2353/chathura/tools/"
                                "XGDAG/Rankings")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "xgdag_pubmed_ablation.tsv"))
    args = parser.parse_args()

    targets = read_genes(os.path.join(HERE, "seeds",
                                      "{}_targets.txt".format(args.disease)))
    rankings = {}
    arms = list(ARMS)
    for arm, tag in ARMS + REPLICATES:
        path = os.path.join(args.rankings, "{}_kiml{}_xgdag_{}.txt".format(
            args.disease, tag, args.method))
        if not os.path.exists(path):
            if (arm, tag) in REPLICATES:
                continue
            raise SystemExit("not found: {}".format(path))
        rankings[arm] = read_ranking(path)
        if (arm, tag) in REPLICATES:
            arms.append((arm, tag))

    baselines = ["baseline"] + [a for a, _ in REPLICATES if a in rankings]
    noise = [(b, a) for i, a in enumerate(baselines) for b in baselines[i + 1:]]
    contrasts = [(a, b, "ablation") for a, b in CONTRASTS] + \
                [(a, b, "noise") for a, b in noise]

    rows = []
    print("disease {}  -  {} targets in the BioGRID namespace\n".format(
        args.disease, len(targets)))

    # Coverage and per-arm scores.
    print("{:10}{:>9}{:>10}{:>12}{:>12}{:>12}{:>12}".format(
        "arm", "genes", "reached", "rankable", "penalised", "penalised", "FE top10%"))
    print("{:10}{:>9}{:>10}{:>12}{:>12}{:>12}{:>12}".format(
        "", "ranked", "targets", "median", "median", "mean", "penalised"))
    print("-" * 77)
    for arm, _ in arms:
        ranking = rankings[arm]
        reached = [g for g in targets if g in ranking]
        record = {"disease": args.disease, "row": "arm", "arm": arm,
                  "genes_ranked": len(ranking), "targets": len(targets),
                  "targets_reached": len(reached)}
        cells = []
        for variant, penalise in (("rankable", False), ("penalised", True)):
            ranks = scaled(ranking, targets, penalise)
            point, bounds = bootstrap(list(ranks.values()), SCALE,
                                      args.n_boot, args.seed)
            for key in KEYS:
                value = point[key] / SCALE if key in RANK_KEYS else point[key]
                record["{}_{}".format(variant, key)] = round(value, 4)
                if key in bounds:
                    lo, hi = bounds[key]
                    if key in RANK_KEYS:
                        lo, hi = lo / SCALE, hi / SCALE
                    record["{}_{}_lo".format(variant, key)] = round(lo, 4)
                    record["{}_{}_hi".format(variant, key)] = round(hi, 4)
            cells.append(record["{}_median_rank_unseen".format(variant)])
        rows.append(record)
        print("{:10}{:>9}{:>10}{:>12.3f}{:>12.3f}{:>12.3f}{:>12.2f}".format(
            arm, len(ranking), len(reached), cells[0], cells[1],
            record["penalised_mean_rank_unseen"],
            record["penalised_fold_enrichment_top_10_pct"]))

    # Did the extra features change the model at all?
    print("\nHow different are the rankings? (all genes, not just targets)")
    print("{:22}{:>10}{:>9}{:>12}{:>12}".format(
        "pair", "spearman", "shared", "top-100", "top-500"))
    print("-" * 65)
    for a, b, kind in contrasts:
        if kind == "noise" and (a, b) == noise[0]:
            print("  - baseline vs baseline (run-to-run) -")
        rho, n = spearman(rankings[a], rankings[b])
        o100 = top_overlap(rankings[a], rankings[b], 100)
        o500 = top_overlap(rankings[a], rankings[b], 500)
        print("{:22}{:>10.3f}{:>9}{:>12}{:>12}".format(
            "{} vs {}".format(a, b), rho, n, o100, o500))
        rows.append({"disease": args.disease, "row": "similarity",
                     "arm": "{} vs {}".format(a, b), "spearman": round(rho, 4),
                     "shared_genes": n, "top100_overlap": o100,
                     "top500_overlap": o500, "kind": kind})

    # Paired contrasts on the common percentile scale.
    print("\nPaired contrasts (A - B; ranks as percentiles, negative favours A;")
    print("FE higher favours A; * = 95% CI excludes zero)")
    for variant, penalise in (("penalised", True), ("rankable", False)):
        print("\n  {} - {}".format(variant, "all targets, unreached put last"
                                   if penalise else "targets both arms reached"))
        print("  {:22}{:>5}{:>26}{:>26}{:>22}".format(
            "contrast", "n", "median pctile [95% CI]", "mean pctile [95% CI]",
            "FE top10% [95% CI]"))
        print("  " + "-" * 101)
        for a, b, kind in contrasts:
            if kind == "noise" and (a, b) == noise[0]:
                print("  - noise floor: baseline vs baseline -")
            ra = scaled(rankings[a], targets, penalise)
            rb = scaled(rankings[b], targets, penalise)
            diffs, n = paired_bootstrap(ra, rb, SCALE, SCALE,
                                        args.n_boot, args.seed)
            record = {"disease": args.disease, "row": "contrast",
                      "arm": "{} - {}".format(a, b), "variant": variant, "n": n,
                      "kind": kind}
            for key in KEYS:
                if key not in diffs:
                    continue
                diff, lo, hi, sig = diffs[key]
                if key in RANK_KEYS:
                    diff, lo, hi = diff / SCALE, lo / SCALE, hi / SCALE
                record[key + "_diff"] = round(diff, 4)
                record[key + "_lo"] = round(lo, 4)
                record[key + "_hi"] = round(hi, 4)
                record[key + "_sig"] = "yes" if sig else "no"
            rows.append(record)

            def cell(key, fmt):
                if key + "_diff" not in record:
                    return "-"
                return ("{" + fmt + "} [{" + fmt + "}, {" + fmt + "}]{}").format(
                    record[key + "_diff"], record[key + "_lo"], record[key + "_hi"],
                    "*" if record[key + "_sig"] == "yes" else " ")
            print("  {:22}{:>5}{:>26}{:>26}{:>22}".format(
                "{} - {}".format(a, b), n,
                cell("median_rank_unseen", ":+.3f"),
                cell("mean_rank_unseen", ":+.3f"),
                cell("fold_enrichment_top_10_pct", ":+.2f")))

    columns = []
    for record in rows:
        for key in record:
            if key not in columns:
                columns.append(key)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print("\nWrote {}".format(args.out))


if __name__ == "__main__":
    main()
