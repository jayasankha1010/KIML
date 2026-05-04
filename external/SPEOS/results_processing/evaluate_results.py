import os
import pandas as pd
import matplotlib.pyplot as plt
import argparse
import numpy as np

# ========================
# Configuration (editable)
# ========================
default_experiment = "Exp_DEE_KIGNN"
compare_from_default = "2022_09"
rank_upper_xlim = 16000  # for barcode plot x-limit
# Changed default log file name as requested (using .tsv for data structure)
RANK_METRICS_FILE = "rank_metrics.tsv" 
# ========================


def calculate_retrieval_metrics(df_ranked, target_genes, total_population_size):
    """
    Calculates comprehensive retrieval metrics for the 'unseen' gene set.
    """
    # 1. Identify Hits
    # Filter the dataframe to just the hits (relevant items)
    hits = df_ranked[df_ranked["hgnc"].isin(target_genes)].copy()
    
    # Get the ranks of the hits, sorted (1-based ranks)
    hit_ranks = hits["rank"].sort_values().values
    num_hits = len(hit_ranks)
    
    metrics = {}
    
    # Store raw counts
    metrics["num_targets_found"] = num_hits
    
    # Handle edge case: No relevant genes found in the list
    if num_hits == 0:
        # Fill zeros for robustness
        metrics["avg_precision"] = 0.0
        metrics["avg_reciprocal_rank_custom"] = 0.0
        for p in [1, 5, 10]:
            metrics[f"fold_enrichment_top_{p}_pct"] = 0.0
            metrics[f"recall_top_{p}_pct"] = 0.0
        for k in [10, 25, 50, 100, 250, 1000]:
            metrics[f"precision_at_{k}"] = 0.0
            metrics[f"recall_at_{k}"] = 0.0
        return metrics

    # ---------------------------------------------------------
    # A. Average Precision (AP)
    # ---------------------------------------------------------
    # Precision at cut-off k is (k_th_hit_index + 1) / rank_of_k_th_hit
    precisions_at_hits = (np.arange(num_hits) + 1) / hit_ranks
    metrics["avg_precision"] = np.mean(precisions_at_hits)

    # ---------------------------------------------------------
    # B. Average Reciprocal Rank (ARR) - Custom Metric
    # ---------------------------------------------------------
    # The mean of (1/rank) for all target items
    metrics["avg_reciprocal_rank_custom"] = np.mean(1.0 / hit_ranks)

    # ---------------------------------------------------------
    # C. Fold Enrichment @ Top X%
    # ---------------------------------------------------------
    # Enrichment = (Observed Recall %) / (Random Recall %)
    percentages = [1, 5, 10]  # 1%, 5%, 10%
    
    for p in percentages:
        cutoff_rank = int(total_population_size * (p / 100.0))
        # Count hits in top cutoff_rank
        hits_in_top = np.sum(hit_ranks <= cutoff_rank)
        
        # Recall observed (Relative to targets found in TSV)
        recall_obs = hits_in_top / num_hits
        
        # Enrichment
        enrichment = recall_obs / (p / 100.0)
        
        metrics[f"fold_enrichment_top_{p}_pct"] = enrichment
        metrics[f"recall_top_{p}_pct"] = recall_obs

    # ---------------------------------------------------------
    # D. Precision and Recall @ K
    # ---------------------------------------------------------
    k_thresholds = [10, 25, 50, 100, 250, 1000]
    
    for k in k_thresholds:
        # Hits within the top k ranks
        hits_at_k = np.sum(hit_ranks <= k)
        
        # Precision @ K = (hits in top K) / K
        prec_k = hits_at_k / k
        
        # Recall @ K = (hits in top K) / (Total Targets present in TSV)
        rec_k = hits_at_k / num_hits
        
        metrics[f"precision_at_{k}"] = prec_k
        metrics[f"recall_at_{k}"] = rec_k
        
    return metrics


def write_summary_row(row_dict, summary_path):
    """Create TSV if missing (with header), then append a single row."""
    df_row = pd.DataFrame([row_dict])
    
    if not os.path.exists(summary_path):
        # File doesn't exist: Write with Header
        df_row.to_csv(summary_path, sep="\t", index=False, header=True)
        print(f"\n[Log] Created new file and logged results -> {summary_path}")
    else:
        try:
            # Read existing header
            existing_df = pd.read_csv(summary_path, sep="\t")
            existing_columns = existing_df.columns
            
            # Check if the new row has any columns that are NOT in the file
            new_cols = set(df_row.columns) - set(existing_columns)
            
            if new_cols:
                # Safe Mode: If new columns exist, we MUST read + merge + overwrite
                # otherwise the TSV structure breaks (headers won't match columns)
                print(f"\n[Log] New metrics detected {new_cols}. Merging and rewriting file...")
                updated_df = pd.concat([existing_df, df_row], ignore_index=True)
                updated_df.to_csv(summary_path, sep="\t", index=False)
                print(f"[Log] File successfully updated with new columns -> {summary_path}")
            else:
                # Fast Mode: If columns match (or are subset), just append
                # Reorder df_row to match existing file order exactly
                df_row = df_row.reindex(columns=existing_columns)
                df_row.to_csv(summary_path, sep="\t", index=False, mode="a", header=False)
                print(f"\n[Log] Appended results to -> {summary_path}")
                
        except Exception as e:
            print(f"\n[Error] Could not append to file: {e}")


def calculate_ranks(experiment=default_experiment, compare_from=compare_from_default, disease="dee", comment=""):
    # tsv_file = f"{experiment}_probabilities.tsv"
    tsv_file = f"./results_processing/{experiment}_probabilities.tsv"

    # ---- Select gene list based on disease
    # (Mapping abbreviated for brevity, same as before)
    disease_map = {
        "dee": "./../../data/kiml_data/diseases/DEE-2025_03_vs_2022_09.txt",
        "ad_dee": "./../../data/kiml_data/diseases/AD_DEE-2022_09_to_2025_03.txt",
        "ar_dee": "./../../data/kiml_data/diseases/AR_DEE-2022_09_to_2025_03.txt",
        "aminoacidopathy": "./../../data/kiml_data/diseases/Aminoacidopathy-2025_06_vs_2022_09.txt",
        "arthrogryposis": "./../../data/kiml_data/diseases/Arthrogryposis-2025_06_vs_2022_09.txt",
        "ataxia": "./../../data/kiml_data/diseases/Ataxia_paed-2025_06_vs_2022_09.txt",
        "cp": "./../../data/kiml_data/diseases/CP-2025_06_vs_2022_09.txt",
        "intellectual_disability": "./../../data/kiml_data/diseases/Intellectual-disability-2025_06_vs_2022_09.txt",
        "microcephaly": "./../../data/kiml_data/diseases/Microcephaly-2025_06_vs_2022_09.txt",
        "mnd": "./../../data/kiml_data/diseases/MND-2025_06_vs_2022_09.txt", 
        "skeletal_dysplasia": "./../../data/kiml_data/diseases/Skeletal-dysplasia-diff-2025_06_vs_2022_09.txt",
        "platelet_disorder": "./../../data/kiml_data/diseases/Bleeding_and_Platelet_Disorders-2026-02_vs_2022-09.txt",
        "bone_marrow_failure": "./../../data/kiml_data/diseases/Bone_Marrow_Failure-2026-02_vs_2022-09.txt",
        "cataract": "./../../data/kiml_data/diseases/Cataract-2026-02_vs_2022-09.txt"
    }

    base_path = "./"
    
    if disease.lower() not in disease_map:
        raise ValueError(f"Unknown disease: {disease}. Available: {list(disease_map.keys())}")
        
    gene_list_file = os.path.join(base_path, disease_map[disease.lower()])

    # ---- Load data
    df = pd.read_csv(tsv_file, sep="\t")
    df = df.sort_values(by="avg_probability", ascending=False)
    df_og = df.copy()

    # ---- Unseen positives
    df_unseen = df[df["truth"] != 1].copy()
    
    # Recalculate ranks relative to this specific unseen universe
    df_unseen["rank"] = df_unseen["avg_probability"].rank(ascending=False, method="first").astype(int)
    total_unseen_population = len(df_unseen)

    with open(gene_list_file, "r") as f:
        gene_list = {line.strip() for line in f}

    df_unseen["new_status"] = df_unseen["hgnc"].isin(gene_list)
    ranks_unseen = df_unseen.loc[df_unseen["new_status"], "rank"]
    
    mean_rank_unseen = ranks_unseen.mean()
    median_rank_unseen = ranks_unseen.median()
    n_unseen_in_list = int(ranks_unseen.shape[0])

    # ==========================================
    # Calculate Comprehensive Metrics
    # ==========================================
    advanced_metrics = calculate_retrieval_metrics(
        df_ranked=df_unseen,
        target_genes=gene_list,
        total_population_size=total_unseen_population
    )
    
    # ---- PRINT ALL METRICS TO TERMINAL ----
    print("\n" + "="*40)
    print(f" RESULTS SUMMARY: {experiment} ({disease})")
    print("="*40)
    print(f"Total Universe Size:   {total_unseen_population}")
    print(f"Targets Found in TSV:  {advanced_metrics['num_targets_found']}")
    print(f"Mean Rank (Unseen):    {mean_rank_unseen:.2f}")
    print(f"Median Rank (Unseen):  {median_rank_unseen:.2f}")
    print("-" * 40)
    print(f"Average Precision (AP): {advanced_metrics.get('avg_precision', 0):.4f}")
    print(f"Avg Reciprocal Rank:    {advanced_metrics.get('avg_reciprocal_rank_custom', 0):.4f}")
    print("-" * 40)
    print("Fold Enrichment:")
    for p in [1, 5, 10]:
        val = advanced_metrics.get(f'fold_enrichment_top_{p}_pct', 0)
        print(f"  @ Top {p}%:  {val:.2f}x")
    print("-" * 40)
    print("Precision & Recall @ K:")
    for k in [10, 25, 50, 100, 250, 1000]:
        prec = advanced_metrics.get(f'precision_at_{k}', 0)
        rec = advanced_metrics.get(f'recall_at_{k}', 0)
        print(f"  @ {k:<4} -> Precision: {prec:.4f} | Recall: {rec:.4f}")
    print("="*40 + "\n")


    # ---- Plot for unseen
    plt.figure(figsize=(10, 1))
    plt.eventplot(ranks_unseen, orientation="horizontal", lineoffsets=1,
                  linelengths=0.5, linewidths=0.5, colors="black")
    plt.axvline(mean_rank_unseen, color="red", linestyle="--", linewidth=1.5, label=f"Mean ({mean_rank_unseen:.2f})")
    plt.axvline(median_rank_unseen, color="blue", linestyle="--", linewidth=1.5, label=f"Median ({median_rank_unseen:.2f})")

    plt.text(0.25, -0.8, f"Mean rank = {mean_rank_unseen:.2f}",
             transform=plt.gca().transAxes, fontsize=6, ha="left", va="bottom", color="red")
    plt.text(0.05, -0.8, f"Median rank = {median_rank_unseen:.2f}",
             transform=plt.gca().transAxes, fontsize=6, ha="left", va="bottom", color="blue")

    plt.xlim(-100, rank_upper_xlim)
    plt.title(f"Barcode: Ranks of new {disease} genes ({compare_from} - 2025_03) - {experiment}")
    plt.xlabel("Rank")
    plt.yticks([])
    plt.grid(axis="x", linestyle="--", alpha=0.7)
    out_unseen = f"{experiment}_barcode_plot_with_rank_speos_{compare_from}_to_25_03_{disease}.png"
    plt.savefig(out_unseen, dpi=300, bbox_inches="tight")
    
    # ---- Seen positives (truth == 1)
    df_seen = df_og.copy()
    df_seen["rank"] = df_seen["avg_probability"].rank(ascending=False, method="first").astype(int)
    seen_ranks = df_seen.loc[df_seen["truth"] == 1, "rank"]
    mean_rank_seen = seen_ranks.mean()
    median_rank_seen = seen_ranks.median()
    n_seen_true_positives = int((df_og["truth"] == 1).sum())

    plt.figure(figsize=(10, 1))
    plt.eventplot(seen_ranks, orientation="horizontal", lineoffsets=1,
                  linelengths=0.5, linewidths=0.5, colors="black")
    plt.axvline(mean_rank_seen, color="red", linestyle="--", linewidth=1.5, label=f"Mean ({mean_rank_seen:.2f})")
    plt.axvline(median_rank_seen, color="blue", linestyle="--", linewidth=1.5, label=f"Median ({median_rank_seen:.2f})")

    plt.text(0.25, -0.8, f"Mean rank = {mean_rank_seen:.2f}",
             transform=plt.gca().transAxes, fontsize=6, ha="left", va="bottom", color="red")
    plt.text(0.05, -0.8, f"Median rank = {median_rank_seen:.2f}",
             transform=plt.gca().transAxes, fontsize=6, ha="left", va="bottom", color="blue")

    plt.xlim(-100, rank_upper_xlim)
    plt.title(f"Barcode: Ranks of seen {disease} genes ({compare_from}) - {experiment}")
    plt.xlabel("Rank")
    plt.yticks([])
    plt.grid(axis="x", linestyle="--", alpha=0.7)
    out_seen = f"{experiment}_barcode_plot_with_rank_seen_{compare_from}_{disease}.png"
    plt.savefig(out_seen, dpi=300, bbox_inches="tight")

    # ---- Prepare Row for Logging
    summary_row = {
        "experiment": experiment,
        "comment": comment,
        "disease": disease,
        "mean_rank_unseen": round(mean_rank_unseen, 4) if pd.notna(mean_rank_unseen) else None,
        "median_rank_unseen": round(median_rank_unseen, 4) if pd.notna(median_rank_unseen) else None,
        "n_unseen_in_list": n_unseen_in_list,
        "compare_from": compare_from,
        # Merging new metrics
        **advanced_metrics,
        "mean_rank_seen": round(mean_rank_seen, 4) if pd.notna(mean_rank_seen) else None,
        "median_rank_seen": round(median_rank_seen, 4) if pd.notna(median_rank_seen) else None,
        "n_seen_true_positives": n_seen_true_positives,
    }
    
    # Round all float values in summary_row for cleaner TSV
    for k, v in summary_row.items():
        if isinstance(v, float):
            summary_row[k] = round(v, 4)

    write_summary_row(summary_row, summary_path=RANK_METRICS_FILE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate barcode plot and log rank summary with advanced metrics.")
    parser.add_argument("-e", "--experiment", type=str, default=default_experiment, help="Experiment prefix for TSV files")
    parser.add_argument("-c", "--compare_from", type=str, default=compare_from_default, help="Compare-from tag (e.g., 2022_09)")
    parser.add_argument("-d", "--disease", type=str, required=True, help="Disease name (dee, ad, ar)")
    parser.add_argument("--comment", type=str, default="", help="Optional comment to add to summary")
    parser.add_argument("--summary", type=str, default=RANK_METRICS_FILE, help="Path to summary TSV (default: rank_metrics.tsv)")
    args = parser.parse_args()

    if args.summary != RANK_METRICS_FILE:
        RANK_METRICS_FILE = args.summary

    calculate_ranks(args.experiment, args.compare_from, args.disease, args.comment)