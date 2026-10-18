import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
# --- Input file paths ---
#median=1538, mean=2409
# csv_file = "Mantis_aminoacidopathy.csv"
# gene_list_file = "Aminoacidopathy-2025-06.txt"
# output_file = "./results/mantis_results_aminoacidopathy.csv"

#median=1515, mean=2161
# csv_file = "mantis-aminoacidopathy-mantis-pubmed.csv"
# gene_list_file = "Aminoacidopathy-2025-06.txt"
# output_file = "./results/mantis_results_aminoacidopathy_with_pubmed.csv"

# csv_file = "mantis-intellectual-disability.csv"
# gene_list_file = "Intellectual-disability-2025-06.txt"
# output_file = "./results/mantis_results_intel_disability.csv"

# median=2896, mean=3650
# csv_file = "mantis-intellectual-disability-mantis-pubmed.csv"
# gene_list_file = "Intellectual-disability-2025-06.txt"
# output_file = "./results/mantis_results_intel_disability_with_pubmed.csv"

# csv_file = "mantis-microcephaly.csv"
# gene_list_file = "Microcephaly-2025-06.txt"
# output_file = "./results/mantis_results_microcephaly.csv"

#median=2691, mean=3621
# csv_file = "mantis-microcephaly-mantis-pubmed.csv"
# gene_list_file = "Microcephaly-2025-06.txt"
# output_file = "./results/mantis_results_microcephaly_with_pubmed.csv"

# csv_file = "mantis-cp.csv"
# gene_list_file = "CP-2025-06.txt"
# output_file = "./results/mantis_results_cp.csv"

# median-1450, mean=2836
# csv_file = "mantis-cp-mantis-pubmed.csv"
# gene_list_file = "CP-2025-06.txt"
# output_file = "./results/mantis_results_cp_with_pubmed.csv"

# csv_file = "mantis-arthrogryposis.csv"
# gene_list_file = "Arthrogryposis-2025-06.txt"
# output_file = "./results/mantis_results_arthrogryposis.csv"

# median=2492, mean=3568
# csv_file = "mantis-arthrogryposis-mantis-pubmed.csv"
# gene_list_file = "Arthrogryposis-2025-06.txt"
# output_file = "./results/mantis_results_arthrogryposis_with_pubmed.csv"

#median=5710, mean=5641
# csv_file = "mantis-ataxia.csv"
# gene_list_file = "Ataxia_paed-2025-06.txt"
# output_file = "./results/mantis_results_ataxia.csv"

# median=2607, mean=5286
# csv_file = "mantis-ataxia-mantis-pubmed.csv"
# gene_list_file = "Ataxia_paed-2025-06.txt"
# output_file = "./results/mantis_results_ataxia_with_pubmed.csv"

# csv_file = "mantis-mnd.csv"
# gene_list_file = "MND-2025-06.txt"
# output_file = "./results/mantis_results_mnd.csv"

# # median=669, mean=2501
# csv_file = "mantis-mnd-mantis-pubmed.csv"
# gene_list_file = "MND-2025-06.txt"
# output_file = "./results/mantis_results_mnd_with_pubmed.csv"

# csv_file = "mantis-skeletal-dysplasia.csv"
# gene_list_file = "Skeletal-dysplasia-2025-06.txt"
# output_file = "./results/mantis_results_skeletal_dysplasia.csv"

# median=926, mean=2457
# csv_file = "mantis-skeletal-dysplasia-mantis-pubmed.csv"
# gene_list_file = "Skeletal-dysplasia-2025-06.txt"
# output_file = "./results/mantis_results_skeletal_dysplasia_with_pubmed.csv"



# gene_list_file = "dee_2025_03.txt"
# csv_file = "dee_biallelic.csv"
# gene_list_file = "only_in_AR_dee_2025.txt"
# output_file = "./results/new_ar_bi_ranked.csv"

# This gives good results; median=718, mean=1130
# csv_file = "mantis-ad-2022.csv"
# gene_list_file = "ad_dee_2025_03.txt"
# output_file = "./results/mantis_ad_dee-2022.csv"

# This gives good results; median=710, mean=1095
# csv_file = "mantis-ad-dee-mantis-pubmed.csv"
# gene_list_file = "ad_dee_2025_03.txt"
# output_file = "./results/mantis_ad_dee-with_pubmed.csv"

# # This gives good results too; median=1779, mean=2895
# csv_file = "mantis-ar-2022.csv"
# gene_list_file = "ar_dee_2025_03.txt"
# output_file = "./results/mantis_ar_dee-2022.csv"

# # This gives good results too; median=1779, mean=2895
# csv_file = "mantis-ar-dee-mantis-pubmed.csv"
# gene_list_file = "ar_dee_2025_03.txt"
# output_file = "./results/mantis_ar_dee-2022_with_pubmed.csv"


# # False : median=2201, mean=3283  # only with mantis datasets
# # Corrected : median=2201, mean=3283 # with mantis datasets
# csv_file = "mantis_dee_2022_aug4.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/mantis_dee_original.csv"

# # False : median=1115, mean=1996 # with mantis datasets and pubmed
# # Corrected : median=1230, mean=2226 # with mantis datasets and pubmed
# csv_file = "mantis-dee-with-pubmed.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/mantis_dee_with_pubmed.csv"

# #False : median=1066, mean=1988.  # with mantis datasets and pubmed and expression
# #Corrected : median=1203, mean=2187.  # with mantis datasets and pubmed and expression
# csv_file = "mantis-dee-mantis-pubmed-expression.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/mantis_dee_mantis_pubmed_expression.csv"

# csv_file = "mantis-dee-pubmed-expression.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/mantis_dee_pubmed_expression.csv"


# Median rank : 4726.0
# Mean rank : 7372.176245210728
# csv_file = "mantis_dee_toppgene_chi2_50.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/mantis_dee_toppgene_chi2_best50.csv"

# Median rank : 4149.0
# Mean rank : 6719.961685823755
# csv_file = "mantis_dee_toppgene_chi2_50_plus_pubmed_embeddings.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/mantis_dee_toppgene_chi2_50_plus_pubmed_embeddings.csv"


# Median rank : 3959.0
# Mean rank : 7104.701149425287
# csv_file = "rf_dee_toppgene_boruta.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/mantis_dee_toppgene_chi2_50_plus_pubmed_embeddings.csv"

# Median rank : 4521.0
# Mean rank : 6824.088122605364
# csv_file = "rf_dee_toppgene_boruta_with_pubmed.csv"
# gene_list_file = "dee_2025_03.txt"
# output_file = "./results/rf_dee_toppgene_boruta_with_pubmed.csv"

csv_file = "rf_ad_dee_toppgene_boruta.csv"
gene_list_file = "ad_dee_2025_03.txt"
output_file = "./results/rf_ad_dee_toppgene_boruta.csv"



# --- Load CSV ---
df = pd.read_csv(csv_file)
print(f"Full df, remaining: {df.shape[0]} rows")

# --- Remove known genes before ranking ---
df_filtered = df[df["Known Gene"] != 1]
# df_filtered = df
print(f"Filtered out known genes, remaining: {df_filtered.shape[0]} rows")
# df_filtered = df[df["Known Gene"].astype(str).str.lower() != "true"]

df_filtered = df_filtered.drop_duplicates(subset="Gene Name", keep="first")
print(f"Removed duplicate gene names, remaining: {df_filtered.shape[0]} rows")

# --- Sort and rank ---
df_sorted = df_filtered.sort_values(by="Mantis-ml Prediction Probability", ascending=False).reset_index(drop=True)
df_sorted["Rank"] = df_sorted.index + 1

# --- Load gene list from text file ---
with open(gene_list_file, "r") as f:
    gene_list = {line.strip() for line in f if line.strip()}

# --- Filter for genes in gene list ---
selected_genes_df = df_sorted[df_sorted["Gene Name"].isin(gene_list)]

# --- Save selected genes with ranks ---
selected_genes_df[["Gene Name", "Rank"]].to_csv(output_file, index=False)

# --- Calculate and print stats ---
mean_rank = selected_genes_df["Rank"].mean()
median_rank = selected_genes_df["Rank"].median()
total_in_bins = selected_genes_df["Rank"].between(0, 20000).sum()
print(f"Total genes in bins (0-20,000): {total_in_bins}")

positive_genes = selected_genes_df["Gene Name"].tolist()
with open("positive_genes_mantis.txt", "w") as f:
    for gene in positive_genes:
        f.write(f"{gene}\n")

print(f"Mean rank of selected genes (excluding known genes): {mean_rank}")
print(f"Median rank of selected genes (excluding known genes): {median_rank}")

print("---------------------------------------------------------")
print(f"Median rank : {median_rank}")
print(f"Mean rank : {mean_rank}")
print("---------------------------------------------------------")


# --- Set bin edges from 0 to 20,000 with width = 500 ---
bins = list(range(0, 20001, 500))  # 0 to 20000 inclusive

# --- Plot with annotations ---
plt.figure(figsize=(10, 6))
ax = sns.histplot(
    selected_genes_df["Rank"],
    bins=bins,
    kde=False,
    color="skyblue",
    edgecolor="black"
)

# Annotate each bar with its count
for patch in ax.patches:
    height = patch.get_height()
    if height > 0:
        ax.text(
            patch.get_x() + patch.get_width() / 2,  # x position: center of the bar
            height,                                 # y position: top of the bar
            int(height),                            # label: count as integer
            ha='center', va='bottom', fontsize=9
        )

# Final formatting
ax.set_title("Distribution of Ranks for Selected Genes (0–20,000, Bin Size = 500)")
ax.set_xlabel("Rank")
ax.set_ylabel("Count")
ax.set_xticks(bins[::2])  # show every other bin label for readability
ax.set_xticklabels(bins[::2], rotation=45)
ax.set_xlim(0, 20000)
plt.tight_layout()
# plt.show()
# plt.close()

# --- Box and Whisker Plot for distribution ---
plt.figure(figsize=(8, 5))
sns.boxplot(
    x=selected_genes_df["Rank"],
    color="lightgreen",
    orient="h",
    showmeans=True,
    meanprops={
        "marker": "o",
        "markerfacecolor": "red",
        "markeredgecolor": "black",
        "markersize": 6
    }
)
plt.title("Box and Whisker Plot of Selected Gene Ranks")
plt.xlabel("Rank")
plt.xlim(0, 20000)  # adjust based on your rank range
plt.tight_layout()

# Save the plot to file
plt.savefig("./results/boxplot_selected_genes.png", dpi=300)
plt.close()