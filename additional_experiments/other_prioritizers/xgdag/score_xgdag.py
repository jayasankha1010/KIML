"""
Score an XGDAG ranking with the revision's metrics (R1.8 / R3.2).

XGDAG output is a plain ranked gene list, one symbol per line, best first -
so rank is line number. Metrics come from revision_analysis, the same module
every other result in this revision uses, so definitions cannot drift.

THREE THINGS NEED CARE, and all three are reported rather than smoothed over.

1. XGDAG DOES NOT RANK EVERY GENE. The ranking comes out of explanation
   subgraphs, so it covers only the genes the explainer reached - the gate run
   on C0009402 produced 4,947 of a 6,628-gene reference. Targets outside it
   cannot be ranked at all. Scoring only the covered ones would quietly reward
   the method for the omission, so both figures are given: "rankable" uses the
   covered targets, "penalised" puts the rest past the end of the list, which
   is what a user actually experiences.

2. GENE NAMESPACE. The ranking is in the namespace of NIAPU's BioGRID file,
   which predates a batch of HGNC renames (AARS1 is AARS there). The target
   list must be in the same namespace, which is why make_seed_files.py wrote
   <disease>_targets.txt alongside the seed file - use that, not the raw
   PanelApp list.

3. UNIVERSE. XGDAG ranks within BioGRID's largest connected component, not
   our 17,282-gene universe, so a raw median rank is not comparable with
   Table 1. universe_size is on every row and a percentile is reported
   alongside; any comparison against KIML should be paired on shared targets.

Usage:
    python score_xgdag.py --disease dee \
        --ranking /path/to/XGDAG/Rankings/dee_kiml_xgdag_gnnexplainer.txt
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REVISION = os.path.join(ROOT, "additional_experiments", "revision_runs")
sys.path.insert(0, REVISION)
from revision_analysis import bootstrap  # noqa: E402

SEEDS_DIR = os.path.join(HERE, "seeds")


def read_ranking(path):
    """gene -> rank, from a one-symbol-per-line ranked list."""
    ranks, seen = {}, 0
    with open(path) as handle:
        for line in handle:
            gene = line.strip().split()[0] if line.strip() else ""
            if gene and gene not in ranks:
                seen += 1
                ranks[gene] = seen
    return ranks


def read_genes(path):
    with open(path) as handle:
        return [line.strip() for line in handle if line.strip()]


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disease", required=True)
    parser.add_argument("--ranking", required=True)
    parser.add_argument("--method", default="gnnexplainer")
    parser.add_argument("--targets", default=None,
                        help="defaults to seeds/<disease>_targets.txt, which is "
                             "already in the BioGRID namespace")
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "xgdag_metrics.tsv"))
    args = parser.parse_args()

    targets_path = args.targets or os.path.join(
        SEEDS_DIR, "{}_targets.txt".format(args.disease))
    for path in (args.ranking, targets_path):
        if not os.path.exists(path):
            raise SystemExit("not found: {}".format(path))

    ranking = read_ranking(args.ranking)
    targets = read_genes(targets_path)
    universe = len(ranking)

    rankable = sorted(g for g in targets if g in ranking)
    unrankable = sorted(set(targets) - set(ranking))

    # Genes dropped by the symbol mapping never reached the ranking at all;
    # count them separately from genes the explainer simply did not reach.
    unmapped_path = os.path.join(SEEDS_DIR, "{}_unmappable.txt".format(args.disease))
    n_unmapped = len(read_genes(unmapped_path)) if os.path.exists(unmapped_path) else 0

    print("disease          : {}".format(args.disease))
    print("ranking          : {} genes".format(universe))
    print("targets          : {} in the BioGRID namespace".format(len(targets)))
    print("  rankable       : {}".format(len(rankable)))
    print("  not in ranking : {}  (explainer did not reach them)".format(len(unrankable)))
    if n_unmapped:
        print("  unmapped       : {}  (lost earlier, to HGNC renames)".format(n_unmapped))

    if not rankable:
        raise SystemExit("\nNo target is rankable - check the namespace of the "
                         "target list against the ranking.")

    results = []
    print("\n{:12}{:>9}{:>11}{:>10}  {}".format(
        "variant", "targets", "median", "pctile", "95% CI"))
    print("-" * 60)
    for variant in ("rankable", "penalised"):
        if variant == "rankable":
            hits = [ranking[g] for g in rankable]
            size = universe
        else:
            hits = ([ranking[g] for g in rankable]
                    + [universe + 1] * len(unrankable))
            size = universe + len(unrankable)

        point, bounds = bootstrap(hits, size, args.n_boot, args.seed)
        record = {"disease": args.disease, "method": "XGDAG",
                  "explainer": args.method, "variant": variant,
                  "n_targets_total": len(targets),
                  "n_targets_scored": len(hits),
                  "n_unrankable": len(unrankable),
                  "n_unmapped_earlier": n_unmapped,
                  "universe_size": size, "n_boot": args.n_boot,
                  "median_rank_percentile": round(
                      point["median_rank_unseen"] / size, 4)}
        for key, value in point.items():
            record[key] = round(value, 4)
            if key in bounds:
                record[key + "_lo"] = round(bounds[key][0], 4)
                record[key + "_hi"] = round(bounds[key][1], 4)
        results.append(record)

        ci = bounds.get("median_rank_unseen")
        print("{:12}{:>9}{:>11}{:>10.3f}  {}".format(
            variant, len(hits), "{:g}".format(point["median_rank_unseen"]),
            point["median_rank_unseen"] / size,
            "[{:g}, {:g}]".format(*ci) if ci else "-"))

    columns = []
    for record in results:
        for key in record:
            if key not in columns:
                columns.append(key)
    existing = []
    if os.path.exists(args.out):
        with open(args.out) as handle:
            existing = [r for r in csv.DictReader(handle, delimiter="\t")
                        if not (r.get("disease") == args.disease
                                and r.get("explainer") == args.method)]
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(existing + results)
    print("\nWrote {} -> {}".format(args.out, args.out))
    print("\nNOTE: these ranks are within XGDAG's own universe ({} genes), not "
          "ours.\nCompare against KIML with a paired test on shared targets, "
          "never raw medians.".format(universe))


if __name__ == "__main__":
    main()
