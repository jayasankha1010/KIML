"""
ToppGene as an external comparator (Reviewer 1 comment 8 / Reviewer 3 comment 2).

The reviewers ask how KIML compares against established prioritisers. ToppGene
rankings were produced manually through the web interface, seeded with each
disease's 2022-09 panel, and evaluated here against the genes added to that
panel afterwards - the same temporal split used throughout the revision, with
metrics imported from revision_analysis so definitions cannot drift.

THREE THINGS MAKE THIS COMPARISON AWKWARD, AND ALL THREE ARE REPORTED RATHER
THAN SMOOTHED OVER.

1. ToppGene returns only candidates: the seed genes are already excluded from
   its output. That is convenient - no re-ranking needed - but it means the
   universe is defined by ToppGene, not by us.

2. ToppGene's background is smaller than ours (~14.9k genes against our 16.5k
   unlabelled). Rank-based metrics depend on universe size, so a raw median
   rank flatters whichever method ranks over fewer genes. universe_size is
   reported on every row, and a percentile is reported alongside the rank.

3. Some target genes are absent from ToppGene's background entirely - 30 of 223
   for DEE, and only one of those is recoverable through an HGNC alias. Those
   genes cannot be ranked at all. Scoring ToppGene only on the genes it happens
   to cover would quietly reward it for the omission, so both figures are
   given: "rankable" uses the covered targets only, "penalised" assigns the
   worst possible rank to targets ToppGene cannot return, which is what a user
   actually experiences.

The file-to-disease mapping is VERIFIED, not assumed: because ToppGene excludes
the genes it was seeded with, the correct pairing is the one where almost none
of the 2022-09 panel appears in the ranked output. A mapping that fails that
check is reported and skipped rather than silently scored.

Usage:
    python additional_experiments/other_prioritizers/run_toppgene_metrics.py
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "additional_experiments", "revision_runs"))
from revision_analysis import bootstrap, metrics_from_ranks  # noqa: E402,F401

DISEASES_DIR = os.path.join(ROOT, "data", "kiml_data", "diseases")
TOPPGENE_DIR = os.path.join(HERE, "toppgene")

# ToppGene csv -> (label, 2022-09 seed file, post-split target file)
MAPPING = {
    "ToppGeneData_default_2022.csv": (
        "dee", "DEE-2022_09.txt", "DEE-2025_03_vs_2022_09.txt"),
    "ToppGeneData_DEE_AD.csv": (
        "ad_dee", "AD_DEE-2022_09.txt", "AD_DEE-2022_09_to_2025_03.txt"),
    "ToppGeneData_DEE_AR.csv": (
        "ar_dee", "AR_DEE-2022_09.txt", "AR_DEE-2022_09_to_2025_03.txt"),
    "ToppGeneData_cerebral_palsy.csv": (
        "cp", "CP-2022-09.txt", "CP-2025_06_vs_2022_09.txt"),
    "ToppGeneData_intellectual_disability.csv": (
        "intellectual_disability", "Intellectual-disability-2022-09.txt",
        "Intellectual-disability-2025_06_vs_2022_09.txt"),
    "ToppGeneData_microcephaly.csv": (
        "microcephaly", "Microcephaly-2022-09.txt",
        "Microcephaly-2025_06_vs_2022_09.txt"),
    "ToppGeneData_mnd.csv": (
        "mnd", "MND-2022-09.txt", "MND-2025_06_vs_2022_09.txt"),
    "ToppGeneData_arthrogryposis.csv": (
        "arthrogryposis", "Arthrogryposis-2022-09.txt",
        "Arthrogryposis-2025_06_vs_2022_09.txt"),
    "ToppGeneData_aminoacidopathy.csv": (
        "aminoacidopathy", "Aminoacidopathy-2022-09.txt",
        "Aminoacidopathy-2025_06_vs_2022_09.txt"),
    "ToppGeneData_ataxia_paed.csv": (
        "ataxia_paed", "Ataxia_paed-2022-09.txt",
        "Ataxia_paed-2025_06_vs_2022_09.txt"),
    "ToppGeneData_skeletal_dysplasia.csv": (
        "skeletal_dysplasia", "Skeletal-dysplasia-2022-09.txt",
        "Skeletal-dysplasia-diff-2025_06_vs_2022_09.txt"),
}
# ToppGeneData_ataxia_random.csv is deliberately unmapped: the name indicates a
# randomised-seed control rather than a disease panel, and guessing a pairing
# for it would invent a result.

# Fraction of seed genes allowed to appear in the output before the pairing is
# treated as wrong. ToppGene excludes seeds, so a correct pairing is near zero.
SEED_LEAK_LIMIT = 0.05


def read_genes(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def load_ranking(path):
    """gene -> rank, ordered by ToppGene's own Rank column."""
    rows = []
    with open(path) as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("GeneSymbol") or "").strip()
            try:
                rank = float(row["Rank"])
            except (TypeError, ValueError, KeyError):
                continue
            if symbol:
                rows.append((rank, symbol))
    rows.sort()
    return {symbol: i + 1 for i, (_, symbol) in enumerate(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--toppgene-dir", default=TOPPGENE_DIR)
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "toppgene_metrics.tsv"))
    args = parser.parse_args()

    results = []
    print("{:24}{:>9}{:>9}{:>10}{:>11}{:>10}  {}".format(
        "disease", "universe", "targets", "unrankable", "median", "pctile", "95% CI"))
    print("-" * 94)

    for filename, (disease, seed_file, target_file) in sorted(MAPPING.items()):
        path = os.path.join(args.toppgene_dir, filename)
        if not os.path.exists(path):
            print("{:24}  (missing {})".format(disease, filename))
            continue

        ranking = load_ranking(path)
        seeds = read_genes(os.path.join(DISEASES_DIR, seed_file))
        targets = read_genes(os.path.join(DISEASES_DIR, target_file))

        # Verify the pairing rather than trusting the filename.
        leaked = seeds & set(ranking)
        if seeds and len(leaked) / len(seeds) > SEED_LEAK_LIMIT:
            print("{:24}  SKIPPED - {} of {} seed genes present in the ranking, "
                  "so {} is probably not this disease".format(
                      disease, len(leaked), len(seeds), filename))
            continue
        if leaked:
            # A handful can survive if the panel grew between the scrape and
            # now; drop them so they cannot be counted as candidates.
            for gene in leaked:
                ranking.pop(gene, None)
            ranking = {g: i + 1 for i, g in enumerate(
                sorted(ranking, key=ranking.get))}

        universe = len(ranking)
        rankable = sorted(g for g in targets if g in ranking)
        unrankable = sorted(targets - set(ranking))

        for variant in ("rankable", "penalised"):
            if variant == "rankable":
                hits = [ranking[g] for g in rankable]
                size = universe
            else:
                # Targets ToppGene cannot return are placed past the end of its
                # list, which is what happens to them in practice.
                hits = ([ranking[g] for g in rankable]
                        + [universe + 1] * len(unrankable))
                size = universe + len(unrankable)
            if not hits:
                continue

            point, bounds = bootstrap(hits, size, args.n_boot, args.seed)
            record = {"disease": disease, "method": "ToppGene",
                      "variant": variant, "source_file": filename,
                      "n_targets_total": len(targets),
                      "n_targets_scored": len(hits),
                      "n_unrankable": len(unrankable),
                      "universe_size": size, "n_boot": args.n_boot,
                      "median_rank_percentile": round(
                          point["median_rank_unseen"] / size, 4)}
            for key, value in point.items():
                record[key] = round(value, 4)
                if key in bounds:
                    record[key + "_lo"] = round(bounds[key][0], 4)
                    record[key + "_hi"] = round(bounds[key][1], 4)
            results.append(record)

            if variant == "rankable":
                ci = bounds.get("median_rank_unseen")
                print("{:24}{:>9}{:>9}{:>10}{:>11}{:>10.3f}  {}".format(
                    disease, universe, len(rankable), len(unrankable),
                    "{:g}".format(point["median_rank_unseen"]),
                    point["median_rank_unseen"] / size,
                    "[{:g}, {:g}]".format(*ci) if ci else "-"))

    if not results:
        raise SystemExit("No ToppGene files scored.")

    columns = []
    for record in results:
        for key in record:
            if key not in columns:
                columns.append(key)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    print("\nWrote {} rows ({} diseases x rankable/penalised) -> {}".format(
        len(results), len(results) // 2, args.out))


if __name__ == "__main__":
    main()
