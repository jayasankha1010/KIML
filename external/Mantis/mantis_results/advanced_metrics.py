import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import seaborn as sns

# ==========================================
# CONFIGURATION: LIST OF ALL EXPERIMENTS
# ==========================================
# I have extracted these from your commented-out code.
# You can comment/uncomment specific blocks here to control what runs.

experiments = [
    # {
    #     "disease": "Aminoacidopathy",
    #     "csv_file": "Mantis_aminoacidopathy.csv",
    #     "gene_list_file": "Aminoacidopathy-2025-06.txt",
    #     "output_file": "./results/mantis_results_aminoacidopathy.csv"
    # },
    # {
    #     "disease": "Aminoacidopathy (+PubMed)",
    #     "csv_file": "mantis-aminoacidopathy-mantis-pubmed.csv",
    #     "gene_list_file": "Aminoacidopathy-2025-06.txt",
    #     "output_file": "./results/mantis_results_aminoacidopathy_with_pubmed.csv"
    # },
    # {
    #     "disease": "Intellectual Disability",
    #     "csv_file": "mantis-intellectual-disability.csv",
    #     "gene_list_file": "Intellectual-disability-2025-06.txt",
    #     "output_file": "./results/mantis_results_intel_disability.csv"
    # },
    # {
    #     "disease": "Intellectual Disability (+PubMed)",
    #     "csv_file": "mantis-intellectual-disability-mantis-pubmed.csv",
    #     "gene_list_file": "Intellectual-disability-2025-06.txt",
    #     "output_file": "./results/mantis_results_intel_disability_with_pubmed.csv"
    # },
    # {
    #     "disease": "Microcephaly",
    #     "csv_file": "mantis-microcephaly.csv",
    #     "gene_list_file": "Microcephaly-2025-06.txt",
    #     "output_file": "./results/mantis_results_microcephaly.csv"
    # },
    # {
    #     "disease": "Microcephaly (+PubMed)",
    #     "csv_file": "mantis-microcephaly-mantis-pubmed.csv",
    #     "gene_list_file": "Microcephaly-2025-06.txt",
    #     "output_file": "./results/mantis_results_microcephaly_with_pubmed.csv"
    # },
    # {
    #     "disease": "CP",
    #     "csv_file": "mantis-cp.csv",
    #     "gene_list_file": "CP-2025-06.txt",
    #     "output_file": "./results/mantis_results_cp.csv"
    # },
    # {
    #     "disease": "CP (+PubMed)",
    #     "csv_file": "mantis-cp-mantis-pubmed.csv",
    #     "gene_list_file": "CP-2025-06.txt",
    #     "output_file": "./results/mantis_results_cp_with_pubmed.csv"
    # },
    # {
    #     "disease": "Arthrogryposis",
    #     "csv_file": "mantis-arthrogryposis.csv",
    #     "gene_list_file": "Arthrogryposis-2025-06.txt",
    #     "output_file": "./results/mantis_results_arthrogryposis.csv"
    # },
    # {
    #     "disease": "Arthrogryposis (+PubMed)",
    #     "csv_file": "mantis-arthrogryposis-mantis-pubmed.csv",
    #     "gene_list_file": "Arthrogryposis-2025-06.txt",
    #     "output_file": "./results/mantis_results_arthrogryposis_with_pubmed.csv"
    # },
    # {
    #     "disease": "Ataxia",
    #     "csv_file": "mantis-ataxia.csv",
    #     "gene_list_file": "Ataxia_paed-2025-06.txt",
    #     "output_file": "./results/mantis_results_ataxia.csv"
    # },
    # {
    #     "disease": "Ataxia (+PubMed)",
    #     "csv_file": "mantis-ataxia-mantis-pubmed.csv",
    #     "gene_list_file": "Ataxia_paed-2025-06.txt",
    #     "output_file": "./results/mantis_results_ataxia_with_pubmed.csv"
    # },
    # {
    #     "disease": "MND",
    #     "csv_file": "mantis-mnd.csv",
    #     "gene_list_file": "MND-2025-06.txt",
    #     "output_file": "./results/mantis_results_mnd.csv"
    # },
    # {
    #     "disease": "MND (+PubMed)",
    #     "csv_file": "mantis-mnd-mantis-pubmed.csv",
    #     "gene_list_file": "MND-2025-06.txt",
    #     "output_file": "./results/mantis_results_mnd_with_pubmed.csv"
    # },
    # {
    #     "disease": "Skeletal Dysplasia",
    #     "csv_file": "mantis-skeletal-dysplasia.csv",
    #     "gene_list_file": "Skeletal-dysplasia-2025-06.txt",
    #     "output_file": "./results/mantis_results_skeletal_dysplasia.csv"
    # },
    # {
    #     "disease": "Skeletal Dysplasia (+PubMed)",
    #     "csv_file": "mantis-skeletal-dysplasia-mantis-pubmed.csv",
    #     "gene_list_file": "Skeletal-dysplasia-2025-06.txt",
    #     "output_file": "./results/mantis_results_skeletal_dysplasia_with_pubmed.csv"
    # },
    # {
    #     "disease": "AD DEE (2022)",
    #     "csv_file": "mantis-ad-2022.csv",
    #     "gene_list_file": "ad_dee_2025_03.txt",
    #     "output_file": "./results/mantis_ad_dee-2022.csv"
    # },
    # {
    #     "disease": "AD DEE (+PubMed)",
    #     "csv_file": "mantis-ad-dee-mantis-pubmed.csv",
    #     "gene_list_file": "ad_dee_2025_03.txt",
    #     "output_file": "./results/mantis_ad_dee-with_pubmed.csv"
    # },
    # {
    #     "disease": "AR DEE (2022)",
    #     "csv_file": "mantis-ar-2022.csv",
    #     "gene_list_file": "ar_dee_2025_03.txt",
    #     "output_file": "./results/mantis_ar_dee-2022.csv"
    # },
    # {
    #     "disease": "AR DEE (+PubMed)",
    #     "csv_file": "mantis-ar-dee-mantis-pubmed.csv",
    #     "gene_list_file": "ar_dee_2025_03.txt",
    #     "output_file": "./results/mantis_ar_dee-2022_with_pubmed.csv"
    # },
    # {
    #     "disease": "DEE (Original)",
    #     "csv_file": "mantis_dee_2022_aug4.csv",
    #     "gene_list_file": "dee_2025_03.txt",
    #     "output_file": "./results/mantis_dee_original.csv"
    # },
    # {
    #     "disease": "DEE (+PubMed)",
    #     "csv_file": "mantis-dee-with-pubmed.csv",
    #     "gene_list_file": "dee_2025_03.txt",
    #     "output_file": "./results/mantis_dee_with_pubmed.csv"
    # }
    # # ==========================================
    # # NEW EXPERIMENTS: (only PubMed)
    # # ==========================================
    # {
    #     "disease": "Platelet Disorder (only PubMed)",
    #     "csv_file": "mantis_hl_platelet_disorder.csv",
    #     "gene_list_file": "Bleeding_and_Platelet_Disorders-2026-02.txt",
    #     "output_file": "./results/mantis_results_platelet_disorder_pubmed_only.csv"
    # },
    # {
    #     "disease": "Skeletal Dysplasia (only PubMed)",
    #     "csv_file": "mantis_hl_skeletal_dysplasia.csv",
    #     "gene_list_file": "Skeletal-dysplasia-2025-06.txt",
    #     "output_file": "./results/mantis_results_skeletal_dysplasia_pubmed_only.csv"
    # },
    # {
    #     "disease": "MND (only PubMed)",
    #     "csv_file": "mantis_hl_mnd.csv",
    #     "gene_list_file": "MND-2025-06.txt",
    #     "output_file": "./results/mantis_results_mnd_pubmed_only.csv"
    # },
    # {
    #     "disease": "Microcephaly (only PubMed)",
    #     "csv_file": "mantis_hl_microcephaly.csv",
    #     "gene_list_file": "Microcephaly-2025-06.txt",
    #     "output_file": "./results/mantis_results_microcephaly_pubmed_only.csv"
    # },
    # {
    #     "disease": "Intellectual Disability (only PubMed)",
    #     "csv_file": "mantis_hl_int_disability.csv",
    #     "gene_list_file": "Intellectual-disability-2025-06.txt",
    #     "output_file": "./results/mantis_results_intel_disability_pubmed_only.csv"
    # },
    # {
    #     "disease": "CP (only PubMed)",
    #     "csv_file": "mantis_hl_cp.csv",
    #     "gene_list_file": "CP-2025-06.txt",
    #     "output_file": "./results/mantis_results_cp_pubmed_only.csv"
    # },
    # {
    #     "disease": "Ataxia (only PubMed)",
    #     "csv_file": "mantis_hl_ataxia.csv",
    #     "gene_list_file": "Ataxia_paed-2025-06.txt",
    #     "output_file": "./results/mantis_results_ataxia_pubmed_only.csv"
    # },
    # {
    #     "disease": "Aminoacidopathy (only PubMed)",
    #     "csv_file": "mantis_hl_aminoacidopathy.csv",
    #     "gene_list_file": "Aminoacidopathy-2025-06.txt",
    #     "output_file": "./results/mantis_results_aminoacidopathy_pubmed_only.csv"
    # },
    # {
    #     "disease": "DEE (only PubMed)",
    #     "csv_file": "mantis_hl_dee.csv",
    #     "gene_list_file": "dee_2025_03.txt",
    #     "output_file": "./results/mantis_dee_pubmed_only.csv"
    # },
    # {
    #     "disease": "AR DEE (only PubMed)",
    #     "csv_file": "mantis_hl_ar_dee.csv",
    #     "gene_list_file": "ar_dee_2025_03.txt",
    #     "output_file": "./results/mantis_ar_dee_pubmed_only.csv"
    # },
    # {
    #     "disease": "AD DEE (only PubMed)",
    #     "csv_file": "mantis_hl_ad_dee.csv",
    #     "gene_list_file": "ad_dee_2025_03.txt",
    #     "output_file": "./results/mantis_ad_dee_pubmed_only.csv"
    # }
    
    # ==========================================
    # NEW diseases: (only PubMed) 
    # ==========================================
    # {
    #     "disease": "Platelet Disorder (only PubMed)",
    #     "csv_file": "mantis_hl_platelet_disorder.csv",
    #     "gene_list_file": "Bleeding_and_Platelet_Disorders-2026-02.txt",
    #     "output_file": "./results/mantis_results_platelet_disorder_pubmed_only.csv"
    # },
    # {
    #     "disease": "Cataracts (HL+LL)",
    #     "csv_file": "mantis_hl_ll_cataracts.csv",
    #     "gene_list_file": "Cataract-2026-02.txt",
    #     "output_file": "./results/mantis_results_cataracts_hl_ll.csv"
    # },
    # {
    #     "disease": "Platelet Disorder (HL+LL)",
    #     "csv_file": "mantis_hl_ll_platelet_disorder.csv",
    #     "gene_list_file": "Bleeding_and_Platelet_Disorders-2026-02.txt",
    #     "output_file": "./results/mantis_results_platelet_disorder_hl_ll.csv"
    # },
    # {
    #     "disease": "Bone Marrow Failure (only LL)",
    #     "csv_file": "mantis_ll_bone_marrow_failure.csv",
    #     "gene_list_file": "Bone_Marrow_Failure-2026-02.txt",
    #     "output_file": "./results/mantis_results_bmf_ll.csv"
    # },
    # {
    #     "disease": "Platelet Disorder (only LL)",
    #     "csv_file": "mantis_ll_platelet_disorder.csv",
    #     "gene_list_file": "Bleeding_and_Platelet_Disorders-2026-02.txt",
    #     "output_file": "./results/mantis_results_platelet_disorder_ll.csv"
    # },
    # {
    #     "disease": "Cataracts (only LL)",
    #     "csv_file": "mantis_ll_cataracts.csv",
    #     "gene_list_file": "Cataract-2026-02.txt",
    #     "output_file": "./results/mantis_results_cataracts_ll.csv"
    # },
    # {
    #     "disease": "Bone Marrow Failure (only HL)",
    #     "csv_file": "mantis_hl_bone_marrow_failure.csv",
    #     "gene_list_file": "Bone_Marrow_Failure-2026-02.txt",
    #     "output_file": "./results/mantis_results_bmf_hl.csv"
    # },
    # {
    #     "disease": "Cataracts (only HL)",
    #     "csv_file": "mantis_hl_cataracts.csv",
    #     "gene_list_file": "Cataract-2026-02.txt",
    #     "output_file": "./results/mantis_results_cataracts_hl.csv"
    # },
    # {
    #     "disease": "Bone Marrow Failure (HL+LL)",
    #     "csv_file": "mantis_hl_ll_bone_marrow_failure.csv",
    #     "gene_list_file": "Bone_Marrow_Failure-2026-02.txt",
    #     "output_file": "./results/mantis_results_bmf_hl_ll.csv"
    # },
    {
        "disease": "Arthrogryposis (HL) only",
        "csv_file": "mantis_hl_arthrogryposis.csv",
        "gene_list_file": "Arthrogryposis-2025-06.txt",
        "output_file": "./results/mantis_results_arthrogryposis_hl.csv"
    }
    
    # mantis_hl_arthrogryposis
]

# Output file for consolidated metrics
CONSOLIDATED_METRICS_FILE = "Mantis_Results_Consolidated.tsv"
# ==========================================


def calculate_retrieval_metrics(df_ranked, target_genes, total_population_size):
    """
    Calculates comprehensive retrieval metrics for the 'unseen' gene set.
    """
    # 1. Identify Hits
    hits = df_ranked[df_ranked["Gene Name"].isin(target_genes)].copy()
    
    # Get the ranks of the hits
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
    # Ensure results folder exists
    os.makedirs("./results", exist_ok=True)
    
    all_results = []

    print(f"Starting processing of {len(experiments)} experiments...\n")

    for exp in experiments:
        disease_name = exp["disease"]
        csv_file = exp["csv_file"]
        gene_list_file = exp["gene_list_file"]
        output_file = exp["output_file"]

        print(f"--- Processing: {disease_name} ---")
        
        # 1. Load Data
        if not os.path.exists(csv_file):
            print(f"  [Error] CSV file not found: {csv_file}. Skipping.")
            continue
            
        df = pd.read_csv(csv_file)
        
        # 2. Filter out known genes (Training data)
        # Note: Ensuring we handle "1", 1, "True", "true" correctly
        df["Known Gene"] = df["Known Gene"].astype(str)
        df_filtered = df[~df["Known Gene"].isin(["1", "True", "true", "1.0"])]
        
        # 3. Deduplicate
        df_filtered = df_filtered.drop_duplicates(subset="Gene Name", keep="first")
        
        # 4. Sort and Rank
        df_sorted = df_filtered.sort_values(by="Mantis-ml Prediction Probability", ascending=False).reset_index(drop=True)
        df_sorted["Rank"] = df_sorted.index + 1
        total_population = len(df_sorted)

        # 5. Load External Gene List
        if not os.path.exists(gene_list_file):
            print(f"  [Error] Gene list file not found: {gene_list_file}. Skipping.")
            continue
            
        with open(gene_list_file, "r") as f:
            gene_list = {line.strip() for line in f if line.strip()}

        # 6. Calculate Metrics
        # Extract matching genes to calculate simple Mean/Median
        selected_genes_df = df_sorted[df_sorted["Gene Name"].isin(gene_list)]
        
        mean_rank = selected_genes_df["Rank"].mean()
        median_rank = selected_genes_df["Rank"].median()
        
        # Calculate Advanced Metrics
        adv_metrics = calculate_retrieval_metrics(df_sorted, gene_list, total_population)

        # 7. Save per-disease CSV (optional, as per your original script)
        selected_genes_df[["Gene Name", "Rank"]].to_csv(output_file, index=False)
        
        # 8. Print Summary to Terminal
        print(f"  Total Universe: {total_population}")
        print(f"  Targets Found:  {adv_metrics['num_targets_found']}")
        print(f"  Mean Rank:      {mean_rank:.2f}")
        print(f"  Median Rank:    {median_rank:.2f}")
        print(f"  Avg Precision:  {adv_metrics['avg_precision']:.4f}")
        print(f"  Fold Enrich 1%: {adv_metrics['fold_enrichment_top_1_pct']:.2f}x")
        print("")

        # 9. Append to Results List
        result_row = {
            "Disease_Experiment": disease_name,
            "CSV_File": csv_file,
            "Total_Genes": total_population,
            "Mean_Rank": mean_rank,
            "Median_Rank": median_rank,
            **adv_metrics
        }
        all_results.append(result_row)

    # ==========================================
    # SAVE CONSOLIDATED RESULTS
    # ==========================================
    if all_results:
        results_df = pd.DataFrame(all_results)
        
        # Round floats
        results_df = results_df.round(4)
        
        # Save to TSV
        if not os.path.exists(CONSOLIDATED_METRICS_FILE):
            results_df.to_csv(CONSOLIDATED_METRICS_FILE, sep="\t", index=False)
        else:
            # If file exists, merge/append logic
            try:
                existing_df = pd.read_csv(CONSOLIDATED_METRICS_FILE, sep="\t")
                combined_df = pd.concat([existing_df, results_df], ignore_index=True)
                combined_df.to_csv(CONSOLIDATED_METRICS_FILE, sep="\t", index=False)
            except:
                results_df.to_csv(CONSOLIDATED_METRICS_FILE, sep="\t", mode="a", header=False, index=False)
                
        print(f"SUCCESS: All results logged to {CONSOLIDATED_METRICS_FILE}")
    else:
        print("No experiments were run successfully.")

if __name__ == "__main__":
    main()