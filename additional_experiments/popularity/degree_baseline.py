"""
Network-degree baseline (Reviewer 1, comment 6).

R1.6: "The authors themselves acknowledge that literature-derived knowledge is
biased toward well-studied genes. However, I could not find a simple control for
publication count, literature coverage, or NETWORK DEGREE."

The publication-count control is in popularity_baseline.py. This is the third
limb: rank genes by how many neighbours they have in each network, nothing else,
and score that ranking with the identical protocol. A gene with many interaction
partners is "well connected" in the same way a gene with many papers is
"well studied", and a graph model could in principle be exploiting the former
rather than learning anything disease-specific.

Protocol matches results_processing/evaluate_results.py and the popularity
baseline, so the numbers sit alongside the model runs:

  universe  every gene in the network, minus that disease's pre-split positives
  ranking   descending degree, ties broken deterministically by gene name
  targets   genes added to the panel after 2022-09
  metrics   imported from revision_analysis, with a bootstrap over target genes

Degree is counted on the undirected simple graph: self-loops are dropped and a
reciprocal pair counts once, so a gene's degree is its number of distinct
partners rather than its number of edge records.

Usage:
    python additional_experiments/popularity/degree_baseline.py
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "additional_experiments", "revision_runs"))
from revision_analysis import DISEASE_TARGETS, bootstrap  # noqa: E402

DATA = os.path.join(ROOT, "data", "kiml_data")

# name -> (path, source column, target column, delimiter)
# None columns mean "first two whitespace-separated fields".
NETWORKS = {
    "covaries": (os.path.join(DATA, "networks", "gene_gene_covaries.txt"), None, None, None),
    "interacts": (os.path.join(DATA, "networks", "gene_gene_interacts.txt"), None, None, None),
    "regulates": (os.path.join(DATA, "networks", "gene_gene_regulates.txt"), None, None, None),
    "pathway": (os.path.join(DATA, "networks", "network_pathway.txt"), None, None, None),
    "reactome": (os.path.join(DATA, "networks", "reactome_pathways.txt"), None, None, None),
    "bioplex_293t": (os.path.join(DATA, "ppi", "BioPlex_293T_Network_10K_Dec_2019.tsv"),
                     "SymbolA", "SymbolB", "\t"),
    "bioplex_hct116": (os.path.join(DATA, "ppi", "BioPlex_HCT116_Network_5.5K_Dec_2019.tsv"),
                       "SymbolA", "SymbolB", "\t"),
}

# Mirrors popularity_baseline.py. AD/AR DEE have no stored 2022-09 list.
DISEASE_PRE = {
    "dee": "DEE-2022_09.txt",
    "ad_dee": "AD_DEE-2022_09.txt",
    "ar_dee": "AR_DEE-2022_09.txt",
    "microcephaly": "Microcephaly-2022-09.txt",
    "intellectual_disability": "Intellectual-disability-2022-09.txt",
    "mnd": "MND-2022-09.txt",
    "cp": "CP-2022-09.txt",
    "platelet_disorder": "Bleeding_and_Platelet_Disorders-2022-09.txt",
    "arthrogryposis": "Arthrogryposis-2022-09.txt",
}


def read_gene_list(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def load_degrees(path, source_col, target_col, delimiter):
    """gene -> number of DISTINCT partners in this network."""
    partners = defaultdict(set)
    with open(path, newline="") as handle:
        if source_col:
            reader = csv.DictReader(handle, delimiter=delimiter)
            pairs = ((row.get(source_col), row.get(target_col)) for row in reader)
        else:
            next(handle, None)  # header
            pairs = (line.split()[:2] for line in handle if len(line.split()) >= 2)
        for a, b in pairs:
            if not a or not b or a == b:  # drop self-loops
                continue
            partners[a].add(b)
            partners[b].add(a)  # undirected: a reciprocal pair counts once
    return {gene: len(p) for gene, p in partners.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disease-dir", default=os.path.join(DATA, "diseases"))
    parser.add_argument("--networks", nargs="*", default=sorted(NETWORKS))
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out", default=os.path.join(HERE, "degree_rank_metrics.tsv"))
    args = parser.parse_args()

    print("Loading networks...")
    degrees = {}
    for name in args.networks:
        path, source_col, target_col, delimiter = NETWORKS[name]
        if not os.path.exists(path):
            print("  [skip] {}: {} not found".format(name, os.path.basename(path)))
            continue
        degrees[name] = load_degrees(path, source_col, target_col, delimiter)
        values = degrees[name].values()
        print("  {:16} {:>6} genes, mean degree {:.1f}, max {}".format(
            name, len(degrees[name]), sum(values) / len(values), max(values)))

    results = []
    print("\n{:16}{:24}{:>8}{:>10}  {}".format(
        "network", "disease", "targets", "median", "95% CI"))
    print("-" * 78)

    for name, degree in sorted(degrees.items()):
        for disease, pre_file in sorted(DISEASE_PRE.items()):
            pre_path = os.path.join(args.disease_dir, pre_file)
            target_file = DISEASE_TARGETS.get(disease)
            if not os.path.exists(pre_path) or not target_file:
                continue
            target_path = os.path.join(args.disease_dir, target_file)
            if not os.path.exists(target_path):
                continue

            pre = read_gene_list(pre_path)
            post = read_gene_list(target_path)

            universe = [g for g in degree if g not in pre]
            # Ties are common at low degree, so break them deterministically
            # rather than by dict order, which is not reproducible.
            universe.sort(key=lambda g: (-degree[g], g))
            rank_of = {g: i + 1 for i, g in enumerate(universe)}
            hit_ranks = [rank_of[g] for g in sorted(post) if g in rank_of]
            if len(hit_ranks) < 5:
                continue

            point, bounds = bootstrap(hit_ranks, len(universe), args.n_boot, args.seed)
            record = {"network": name, "disease": disease,
                      "n_targets": len(hit_ranks), "universe_size": len(universe)}
            for key, value in point.items():
                record[key] = round(value, 4)
                if key in bounds:
                    record[key + "_lo"] = round(bounds[key][0], 4)
                    record[key + "_hi"] = round(bounds[key][1], 4)
            results.append(record)

            ci = bounds.get("median_rank_unseen")
            print("{:16}{:24}{:>8}{:>10}  {}".format(
                name, disease, len(hit_ranks),
                "{:g}".format(point["median_rank_unseen"]),
                "[{:g}, {:g}]".format(*ci) if ci else "-"))

    if not results:
        print("\nNothing scored.")
        return

    columns = list(results[0])
    for record in results:
        for key in record:
            if key not in columns:
                columns.append(key)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    print("\nWrote {} rows -> {}".format(len(results), args.out))


if __name__ == "__main__":
    main()
