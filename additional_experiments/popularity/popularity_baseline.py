"""
Popularity baseline for KIML.

Ranks genes purely by how many PubMed papers mention them, then measures where
each disease's post-split genes land. This is the "no machine learning at all"
comparator for the KIGNN / KIRF results in results/GNN_results/rank_metrics.tsv.

Protocol, per disease (mirrors results_processing/evaluate_results.py so the rows
are directly comparable):
  universe  = every gene with a literature record, minus that disease's
              pre-split (2022-09) positives
  ranking   = descending paper count
  targets   = the post-split genes ("*_vs_2022_09"), restricted to the universe
  recall@k  = hits in top k / targets present in the universe

Two caveats this script reports rather than hides:

1. genes_to_ids.csv is capped at 100 PMIDs per gene by the ToppGene API, so the
   most-studied ~28% of genes are tied. Every k below ~5000 falls inside that
   tie, where the result is decided by sort order rather than by popularity.
   We therefore re-score under several random tie-breaks and emit the min/max
   band alongside the median. A metric is only trustworthy if its band is
   narrow relative to the effect being claimed.

2. Counts must respect the 2022-10-01 cutoff, otherwise a gene gets credit for
   papers written *because* it was identified as a disease gene after the split
   -- leakage the GNN and RF models were denied. Pass --articles to enable this.
"""

import argparse
import csv
import os
import random
import statistics
import sys
from datetime import datetime

K_THRESHOLDS = [10, 25, 50, 100, 200, 250, 500, 1000]
PERCENTAGES = [1, 5, 10]
CUTOFF_DEFAULT = "2022-10-01"

# disease -> (pre-split positives, post-split targets).
# A pre-split entry of None means it is derived by subtraction; see DERIVED below.
DISEASE_MAP = {
    "dee": ("DEE-2022_09.txt", "DEE-2025_03_vs_2022_09.txt"),
    "ad_dee": (None, "AD_DEE-2022_09_to_2025_03.txt"),
    "ar_dee": (None, "AR_DEE-2022_09_to_2025_03.txt"),
    "aminoacidopathy": ("Aminoacidopathy-2022-09.txt", "Aminoacidopathy-2025_06_vs_2022_09.txt"),
    "arthrogryposis": ("Arthrogryposis-2022-09.txt", "Arthrogryposis-2025_06_vs_2022_09.txt"),
    "ataxia": ("Ataxia_paed-2022-09.txt", "Ataxia_paed-2025_06_vs_2022_09.txt"),
    "cp": ("CP-2022-09.txt", "CP-2025_06_vs_2022_09.txt"),
    "intellectual_disability": ("Intellectual-disability-2022-09.txt", "Intellectual-disability-2025_06_vs_2022_09.txt"),
    "microcephaly": ("Microcephaly-2022-09.txt", "Microcephaly-2025_06_vs_2022_09.txt"),
    "mnd": ("MND-2022-09.txt", "MND-2025_06_vs_2022_09.txt"),
    "skeletal_dysplasia": ("Skeletal-dysplasia-2022-09.txt", "Skeletal-dysplasia-diff-2025_06_vs_2022_09.txt"),
    "platelet_disorder": ("Bleeding_and_Platelet_Disorders-2022-09.txt", "Bleeding_and_Platelet_Disorders-2026-02_vs_2022-09.txt"),
    "bone_marrow_failure": ("Bone_Marrow_Failure-2022-09.txt", "Bone_Marrow_Failure-2026-02_vs_2022-09.txt"),
    "cataract": ("Cataract-2022-09.txt", "Cataract-2026-02_vs_2022-09.txt"),
}

# AD/AR DEE have no stored 2022-09 list, but the diff is a verified subset of the
# 2025-03 list, so the pre-split set is the difference.
DERIVED = {
    "ad_dee": "AD_DEE-2025_03.txt",
    "ar_dee": "AR_DEE_2025_03.txt",
}


def read_gene_list(path):
    with open(path) as handle:
        return {line.strip() for line in handle if line.strip()}


def load_cutoff_pmids(articles_path, cutoff):
    """Return the set of PubMed IDs published strictly before the cutoff."""
    keep = set()
    skipped = 0
    with open(articles_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                date = datetime.strptime(row["SortPubDate"].strip(), "%Y/%m/%d %H:%M")
            except (ValueError, KeyError):
                skipped += 1
                continue
            if date < cutoff:
                keep.add(row["PubMed ID"].strip())
    print("    {} PMIDs before {} ({} rows had unparseable dates)".format(
        len(keep), cutoff.date(), skipped))
    return keep


def load_counts(genes_csv, allowed_pmids):
    """Map gene -> number of papers, optionally restricted to allowed_pmids."""
    counts = {}
    with open(genes_csv, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if not row:
                continue
            gene = row[0].strip()
            pmids = {pmid.strip() for pmid in row[1:] if pmid.strip()}
            if allowed_pmids is not None:
                pmids &= allowed_pmids
            counts[gene] = len(pmids)
    return counts


def score(ranked_genes, targets, universe_size):
    """Retrieval metrics for one concrete ordering. Mirrors evaluate_results.py."""
    rank_of = {gene: i + 1 for i, gene in enumerate(ranked_genes)}
    hit_ranks = sorted(rank_of[gene] for gene in targets)
    n_hits = len(hit_ranks)

    metrics = {
        "median_rank_unseen": statistics.median(hit_ranks),
        "mean_rank_unseen": sum(hit_ranks) / n_hits,
        # Same definitions as evaluate_results.py, so the columns line up.
        "avg_precision": sum((i + 1) / r for i, r in enumerate(hit_ranks)) / n_hits,
        "avg_reciprocal_rank_custom": sum(1.0 / r for r in hit_ranks) / n_hits,
    }
    for pct in PERCENTAGES:
        cutoff_rank = int(universe_size * (pct / 100.0))
        recall = sum(1 for r in hit_ranks if r <= cutoff_rank) / n_hits
        metrics["fold_enrichment_top_{}_pct".format(pct)] = recall / (pct / 100.0)
        metrics["recall_top_{}_pct".format(pct)] = recall
    for k in K_THRESHOLDS:
        hits_at_k = sum(1 for r in hit_ranks if r <= k)
        metrics["precision_at_{}".format(k)] = hits_at_k / k
        metrics["recall_at_{}".format(k)] = hits_at_k / n_hits
    return metrics


def evaluate_disease(disease, counts, disease_dir, n_seeds):
    pre_file, post_file = DISEASE_MAP[disease]
    post = read_gene_list(os.path.join(disease_dir, post_file))
    if pre_file is None:
        pre = read_gene_list(os.path.join(disease_dir, DERIVED[disease])) - post
    else:
        pre = read_gene_list(os.path.join(disease_dir, pre_file))

    universe = [gene for gene in counts if gene not in pre]
    targets = set(universe) & post
    if not targets:
        print("  [skip] {}: no post-split genes in the universe".format(disease))
        return None

    # Re-score under several tie-breaks. The spread is the honest error bar on
    # every metric, because the capped counts leave a large block of equal scores.
    runs = []
    for seed in range(n_seeds):
        shuffled = universe[:]
        random.Random(seed).shuffle(shuffled)
        shuffled.sort(key=lambda gene: -counts[gene])  # stable: ties keep shuffled order
        runs.append(score(shuffled, targets, len(universe)))

    # Where do the *already known* (pre-split) genes sit on a pure popularity
    # ranking of the full gene set? This is the direct measure of the
    # well-studied-gene bias: if curated disease genes are near the top on paper
    # count alone, literature features carry that bias into any model using them.
    full = list(counts)
    seen_runs = []
    for seed in range(n_seeds):
        shuffled = full[:]
        random.Random(seed).shuffle(shuffled)
        shuffled.sort(key=lambda gene: -counts[gene])
        rank_of = {gene: i + 1 for i, gene in enumerate(shuffled)}
        seen_ranks = [rank_of[gene] for gene in pre if gene in rank_of]
        if seen_ranks:
            seen_runs.append(statistics.median(seen_ranks))

    max_count = max(counts[gene] for gene in universe)
    tied_at_top = sum(1 for gene in universe if counts[gene] == max_count)

    row = {
        "experiment": "Popularity",
        "comment": "popularity_baseline",
        "disease": disease,
        "compare_from": "2022_09",
        "universe_size": len(universe),
        "n_unseen_in_list": len(targets),
        "num_targets_found": len(targets),
        "n_targets_missing_from_literature": len(post) - len(targets),
        "max_paper_count": max_count,
        "n_tied_at_max": tied_at_top,
        "pct_tied_at_max": round(100.0 * tied_at_top / len(universe), 2),
        "n_targets_tied_at_max": sum(1 for gene in targets if counts[gene] == max_count),
        "n_tiebreak_seeds": n_seeds,
        "n_seen_true_positives": len([g for g in pre if g in counts]),
        "median_rank_seen": round(statistics.median(seen_runs), 1) if seen_runs else None,
    }
    for metric in runs[0]:
        values = [run[metric] for run in runs]
        row[metric] = round(statistics.median(values), 4)
        row[metric + "_lo"] = round(min(values), 4)
        row[metric + "_hi"] = round(max(values), 4)
    return row


def write_rows(rows, out_path):
    if not rows:
        print("\nNothing to write.")
        return
    columns = list(rows[0].keys())
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print("\nWrote {} rows -> {}".format(len(rows), out_path))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--genes", default=os.path.join(root, "kiml", "genes_to_ids.csv"),
                        help="gene -> PubMed IDs CSV (ragged; col 0 is the gene)")
    parser.add_argument("--articles", default=None,
                        help="pubmed_articles_v5.csv, for the publication-date cutoff. "
                             "Omit to count all papers regardless of date (leaky).")
    parser.add_argument("--cutoff", default=CUTOFF_DEFAULT,
                        help="count only papers published before this date (YYYY-MM-DD)")
    parser.add_argument("--disease-dir", default=os.path.join(root, "data", "kiml_data", "diseases"))
    parser.add_argument("--diseases", nargs="*", default=sorted(DISEASE_MAP),
                        help="subset of diseases to score (default: all)")
    parser.add_argument("--seeds", type=int, default=20,
                        help="tie-break orderings to average over (default: 20)")
    parser.add_argument("-o", "--out", default=os.path.join(here, "popularity_rank_metrics.tsv"))
    args = parser.parse_args()

    cutoff = datetime.strptime(args.cutoff, "%Y-%m-%d")

    print("=" * 60)
    print(" Popularity baseline")
    print("=" * 60)

    allowed = None
    if args.articles:
        print("\nApplying publication-date cutoff from {}".format(args.articles))
        allowed = load_cutoff_pmids(args.articles, cutoff)
    else:
        print("\n[WARNING] No --articles given: counting papers of ALL dates.")
        print("          Post-split literature leaks into the ranking, which")
        print("          inflates this baseline relative to the ML models.")

    counts = load_counts(args.genes, allowed)
    print("\nLoaded {} genes.".format(len(counts)))
    if not counts:
        sys.exit("No genes loaded; check --genes.")

    top = max(counts.values())
    n_top = sum(1 for v in counts.values() if v == top)
    print("Max paper count {}; {} genes ({:.1f}%) tied there.".format(
        top, n_top, 100.0 * n_top / len(counts)))
    if n_top > 100:
        print("[WARNING] That tie spans ranks 1-{}. Any metric with a cutoff".format(n_top))
        print("          inside it is set by tie-break order, not popularity.")
        print("          Compare the *_lo / *_hi band, not the point estimate.")

    print("\nScoring {} diseases over {} tie-breaks...".format(len(args.diseases), args.seeds))
    rows = []
    for disease in args.diseases:
        if disease not in DISEASE_MAP:
            print("  [skip] unknown disease: {}".format(disease))
            continue
        row = evaluate_disease(disease, counts, args.disease_dir, args.seeds)
        if row is None:
            continue
        rows.append(row)
        print("  {:24} median={:8.1f} [{:.0f}-{:.0f}]  FE@1%={:5.2f} [{:.2f}-{:.2f}]  "
              "r@100={:.3f} [{:.3f}-{:.3f}]  tied@max={:.0f}%".format(
                  disease,
                  row["median_rank_unseen"], row["median_rank_unseen_lo"], row["median_rank_unseen_hi"],
                  row["fold_enrichment_top_1_pct"], row["fold_enrichment_top_1_pct_lo"], row["fold_enrichment_top_1_pct_hi"],
                  row["recall_at_100"], row["recall_at_100_lo"], row["recall_at_100_hi"],
                  row["pct_tied_at_max"]))

    write_rows(rows, args.out)


if __name__ == "__main__":
    main()
