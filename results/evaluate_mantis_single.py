import pandas as pd
import numpy as np
import os
import argparse

def calculate_retrieval_metrics(df_ranked, target_genes, total_population_size):
    """
    Calculates comprehensive retrieval metrics for the 'unseen' gene set.
    """
    hits = df_ranked[df_ranked["Gene_Name"].isin(target_genes)].copy()
    hit_ranks = hits["Rank"].sort_values().values
    num_hits = len(hit_ranks)
    
    metrics = {}
    metrics["num_targets_found"] = num_hits
    
    if num_hits == 0:
        metrics["avg_precision"] = 0.0
        metrics["avg_reciprocal_rank_custom"] = 0.0
        for p in [1, 5, 10]:
            metrics[f"fold_enrichment_top_{p}_pct"] = 0.0
            metrics[f"recall_top_{p}_pct"] = 0.0
        for k in [10, 25, 50, 100, 250, 1000]:
            metrics[f"precision_at_{k}"] = 0.0
            metrics[f"recall_at_{k}"] = 0.0
        return metrics

    # A. Average Precision (AP)
    precisions_at_hits = (np.arange(num_hits) + 1) / hit_ranks
    metrics["avg_precision"] = np.mean(precisions_at_hits)

    # B. Average Reciprocal Rank (ARR)
    metrics["avg_reciprocal_rank_custom"] = np.mean(1.0 / hit_ranks)

    # C. Fold Enrichment @ Top X%
    percentages = [1, 5, 10]
    for p in percentages:
        cutoff_rank = int(total_population_size * (p / 100.0))
        hits_in_top = np.sum(hit_ranks <= cutoff_rank)
        recall_obs = hits_in_top / num_hits
        enrichment = recall_obs / (p / 100.0)
        metrics[f"fold_enrichment_top_{p}_pct"] = enrichment
        metrics[f"recall_top_{p}_pct"] = recall_obs

    # D. Precision and Recall @ K
    k_thresholds = [10, 25, 50, 100, 250, 1000]
    for k in k_thresholds:
        hits_at_k = np.sum(hit_ranks <= k)
        prec_k = hits_at_k / k
        rec_k = hits_at_k / num_hits
        metrics[f"precision_at_{k}"] = prec_k
        metrics[f"recall_at_{k}"] = rec_k
        
    return metrics

def main():
    parser = argparse.ArgumentParser(description="Evaluate a single Mantis experiment.")
    parser.add_argument("-n", "--name", type=str, required=True, help="Clean name of the experiment for logging (e.g., 'DEE_2022')")
    parser.add_argument("-f", "--folder", type=str, required=True, help="Exact Mantis_Out folder name (e.g., 'dee_2022_dee_2022_pubmed_only_1_iter_custom')")
    parser.add_argument("-t", "--targets", type=str, required=True, help="Filename of the validation target list (e.g., 'DEE-2025_03_vs_2022_09.txt')")
    parser.add_argument("--metrics_out", type=str, default="rank_metrics.tsv", help="Consolidated TSV file to append to")
    args = parser.parse_args()

    # --- Build Absolute/Relative Paths dynamically ---
    # Assuming this script lives in KIML/external/Mantis/ or KIML/results_processing/
    # You can adjust these base paths if the script is executed from a different working directory.
    BASE_MANTIS_OUT = "external/Mantis/Mantis_Out"
    BASE_DISEASE_DIR = "data/kiml_data/diseases"
    
    # Construct the exact path deep inside the Mantis_Out folder
    csv_file = os.path.join(
        BASE_MANTIS_OUT, 
        args.folder, 
        "Gene-Predictions", 
        "AllClassifiers.Merged.mantis-ml_predictions.csv"
    )
    
    gene_list_file = os.path.join(BASE_DISEASE_DIR, args.targets)

    print(f"\n--- Evaluating: {args.name} ---")
    
    # 1. Load Data
    if not os.path.exists(csv_file):
        print(f"[Error] Predictions file not found: {csv_file}")
        print(f"[Tip] Verify that the experiment completed and generated the Gene-Predictions folder.")
        return
        
    df = pd.read_csv(csv_file)
    
    # 2. Filter out known genes (Training data)
    df["known_gene"] = df["known_gene"].astype(str)
    df_filtered = df[~df["known_gene"].isin(["1", "True", "true", "1.0"])]
    
    # 3. Deduplicate
    df_filtered = df_filtered.drop_duplicates(subset="Gene_Name", keep="first")
    
    # 4. Sort and Rank
    df_sorted = df_filtered.sort_values(by="mantis_ml_proba", ascending=False).reset_index(drop=True)
    df_sorted["Rank"] = df_sorted.index + 1
    total_population = len(df_sorted)

    # 5. Load External Validation Gene List
    if not os.path.exists(gene_list_file):
        print(f"[Error] Target gene list not found: {gene_list_file}")
        return
        
    with open(gene_list_file, "r") as f:
        gene_list = {line.strip() for line in f if line.strip()}

    # 6. Calculate Metrics
    selected_genes_df = df_sorted[df_sorted["Gene_Name"].isin(gene_list)]
    mean_rank = selected_genes_df["Rank"].mean()
    median_rank = selected_genes_df["Rank"].median()
    adv_metrics = calculate_retrieval_metrics(df_sorted, gene_list, total_population)

    # 7. Print Output
    print(f"  Target File:    {args.targets}")
    print(f"  Total Universe: {total_population}")
    print(f"  Targets Found:  {adv_metrics['num_targets_found']}")
    print(f"  Mean Rank:      {mean_rank:.2f}")
    print(f"  Median Rank:    {median_rank:.2f}")
    print(f"  Avg Precision:  {adv_metrics['avg_precision']:.4f}")
    print(f"  Fold Enrich 1%: {adv_metrics['fold_enrichment_top_1_pct']:.2f}x\n")

    # 8. Append to TSV
    result_row = {
        "experiment": args.name,       
        "disease": args.targets, 
        "Total_Genes": total_population,
        "mean_rank_unseen": round(mean_rank, 4) if pd.notna(mean_rank) else None,    
        "median_rank_unseen": round(median_rank, 4) if pd.notna(median_rank) else None, 
        **{k: round(v, 4) for k, v in adv_metrics.items()}
    }
    
    results_df = pd.DataFrame([result_row])
    
    # Output file logic
    if not os.path.exists(args.metrics_out):
        results_df.to_csv(args.metrics_out, sep="\t", index=False)
    else:
        # Append gracefully handling column alignment
        try:
            existing_df = pd.read_csv(args.metrics_out, sep="\t")
            combined_df = pd.concat([existing_df, results_df], ignore_index=True)
            combined_df.to_csv(args.metrics_out, sep="\t", index=False)
        except:
            results_df.to_csv(args.metrics_out, sep="\t", mode="a", header=False, index=False)

if __name__ == "__main__":
    main()
    