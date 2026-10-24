import pandas as pd
import os

# Load ToppGene file
df = pd.read_csv("ToppGeneData_default_minus_pubmed_dee.csv")
# df = pd.read_csv("ToppGeneData_default_2022.csv")

# Load gene lists
with open("/Users/CULUWITIKEGA/Desktop/CodeBase/Disease_gene_labels/generated/dee_2022_09.txt") as f:
    dee_2022 = set(line.strip() for line in f if line.strip())

with open("/Users/CULUWITIKEGA/Desktop/CodeBase/Disease_gene_labels/generated/2022_09_to_2025_03.txt") as f:
    dee_2022_to_2025 = set(line.strip() for line in f if line.strip())
    
# df = pd.read_csv("ToppGeneData_DEE_AD.csv")

# # Load gene lists
# with open("/Users/CULUWITIKEGA/Desktop/CodeBase/Disease_gene_labels/generated/ad_dee_2022_09.txt") as f:
#     dee_2022 = set(line.strip() for line in f if line.strip())

# with open("/Users/CULUWITIKEGA/Desktop/CodeBase/Disease_gene_labels/generated/ad_dee_2022_09_to_2025_03.txt") as f:
#     dee_2022_to_2025 = set(line.strip() for line in f if line.strip())
    
    
# # Load ToppGene file
# df = pd.read_csv("ToppGeneData_aminoacidopathy.csv")

# # Load gene lists
# with open("/Users/CULUWITIKEGA/Desktop/CodeBase/Disease_gene_labels/generated/Aminoacidopathy-2022-09.txt") as f:
#     dee_2022 = set(line.strip() for line in f if line.strip())

# with open("/Users/CULUWITIKEGA/Desktop/CodeBase/Disease_gene_labels/generated/Aminoacidopathy-2025_06_vs_2022_09.txt") as f:
#     dee_2022_to_2025 = set(line.strip() for line in f if line.strip())

# Remove DEE 2022 genes
df_filtered = df[~df["GeneSymbol"].isin(dee_2022)].copy()

# Re-rank the remaining genes
df_filtered = df_filtered.sort_values(by="Rank").reset_index(drop=True)
df_filtered["ReRank"] = df_filtered.index + 1

# Extract new ranks of DEE 2022–2025 genes
dee_genes_in_filtered = df_filtered[df_filtered["GeneSymbol"].isin(dee_2022_to_2025)]

# Calculate mean and median ranks
mean_rank = dee_genes_in_filtered["ReRank"].mean()
median_rank = dee_genes_in_filtered["ReRank"].median()

print("Mean rank:", mean_rank)
print("Median rank:", median_rank)

# Calculate stats
mean_rank = dee_genes_in_filtered["ReRank"].mean()
median_rank = dee_genes_in_filtered["ReRank"].median()

num_genes_before_2022 = len(dee_2022)
num_genes_after_2022 = len(dee_2022_to_2025)

# Create a summary row
summary_row = {
    "InputFile": "ToppGeneData_DEE_AR.csv",
    "MedianRank": median_rank,
    "MeanRank": mean_rank,
    "GenesBefore2022": num_genes_before_2022,
    "GenesAfter2022": num_genes_after_2022
}

summary_file = "rank_summary.csv"

# If the file exists, append; otherwise, create it
if os.path.exists(summary_file):
    summary_df = pd.read_csv(summary_file)
    summary_df = pd.concat([summary_df, pd.DataFrame([summary_row])], ignore_index=True)
else:
    summary_df = pd.DataFrame([summary_row])

# Save back to CSV
summary_df.to_csv(summary_file, index=False)
