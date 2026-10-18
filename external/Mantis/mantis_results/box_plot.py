#!/usr/bin/env python3
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from textwrap import dedent

# =========================
# Config: pick which CSV per disease
# (Use the base Mantis files; switch to the *_mantis-pubmed.csv by editing here)
# =========================
CONFIG = [
    # label,                               csv_file,                                      gene_list_file
    ("Aminoacidopathy",                    "Mantis_aminoacidopathy.csv",                  "Aminoacidopathy-2025-06.txt"),
    ("Intellectual disability",            "mantis-intellectual-disability.csv",          "Intellectual-disability-2025-06.txt"),
    ("Microcephaly",                       "mantis-microcephaly.csv",                     "Microcephaly-2025-06.txt"),
    ("Cerebral palsy (CP)",                "mantis-cp.csv",                               "CP-2025-06.txt"),
    ("Arthrogryposis",                     "mantis-arthrogryposis.csv",                   "Arthrogryposis-2025-06.txt"),
    ("Ataxia (paediatric)",                "mantis-ataxia.csv",                           "Ataxia_paed-2025-06.txt"),
    ("Motor neuron disease (MND)",         "mantis-mnd.csv",                              "MND-2025-06.txt"),
    ("Skeletal dysplasia",                 "mantis-skeletal-dysplasia.csv",               "Skeletal-dysplasia-2025-06.txt"),
]

# Output paths
OUTPUT_DIR = "./results"
PLOT_PATH = os.path.join(OUTPUT_DIR, "all_diseases_boxplots.png")
STATS_CSV = os.path.join(OUTPUT_DIR, "all_diseases_boxplot_stats.csv")

# Plot window on the rank axis
RANK_XMIN, RANK_XMAX = 0, 20000      # keep consistent across diseases

# Columns expected
COL_GENE = "Gene Name"
COL_KNOWN = "Known Gene"
COL_SCORE = "Mantis-ml Prediction Probability"

# =========================
# Helpers
# =========================
def ensure_results_dir(path):
    os.makedirs(path, exist_ok=True)

def load_gene_list(path):
    with open(path, "r") as f:
        return {line.strip() for line in f if line.strip()}

def compute_ranks(df):
    """Remove known genes, dedupe by gene name, sort by score desc, add Rank."""
    if COL_KNOWN not in df.columns:
        raise KeyError(f"Missing required column: '{COL_KNOWN}'")
    if COL_GENE not in df.columns:
        raise KeyError(f"Missing required column: '{COL_GENE}'")
    if COL_SCORE not in df.columns:
        raise KeyError(f"Missing required column: '{COL_SCORE}'")

    # Remove known genes (keep rows where Known Gene != 1)
    df_filtered = df[df[COL_KNOWN] != 1].copy()

    # Deduplicate by Gene Name, keep first
    df_filtered = df_filtered.drop_duplicates(subset=COL_GENE, keep="first")

    # Sort by prediction probability descending, assign Rank (1 = best)
    df_sorted = df_filtered.sort_values(by=COL_SCORE, ascending=False).reset_index(drop=True)
    df_sorted["Rank"] = df_sorted.index + 1
    return df_sorted

# =========================
# Main
# =========================
def main():
    ensure_results_dir(OUTPUT_DIR)

    # Collect per-disease rank vectors
    long_rows = []       # for plotting (Disease, Rank)
    stats_rows = []      # for CSV summary

    skipped = []

    for label, csv_file, gene_list_file in CONFIG:
        # Check files exist
        if not os.path.exists(csv_file):
            skipped.append((label, f"CSV not found: {csv_file}"))
            continue
        if not os.path.exists(gene_list_file):
            skipped.append((label, f"Gene list not found: {gene_list_file}"))
            continue

        try:
            df = pd.read_csv(csv_file)
            ranked = compute_ranks(df)
            gene_list = load_gene_list(gene_list_file)

            # Select only the target gene list
            selected = ranked[ranked[COL_GENE].isin(gene_list)].copy()

            if selected.empty:
                skipped.append((label, "No selected genes after filtering"))
                continue

            # Append to long-form for plotting
            for r in selected["Rank"].tolist():
                long_rows.append({"Disease": label, "Rank": r})

            # Summaries
            stats_rows.append({
                "Disease": label,
                "N_selected": len(selected),
                "Rank_mean": selected["Rank"].mean(),
                "Rank_median": selected["Rank"].median(),
                "Rank_min": selected["Rank"].min(),
                "Rank_max": selected["Rank"].max(),
            })

        except Exception as e:
            skipped.append((label, f"Error: {e}"))

    if not long_rows:
        msg = "No data to plot. Check file paths and columns."
        if skipped:
            msg += "\nProblems encountered:\n" + "\n".join([f"- {d}: {why}" for d, why in skipped])
        raise RuntimeError(msg)

    # Build DataFrames
    long_df = pd.DataFrame(long_rows)
    stats_df = pd.DataFrame(stats_rows).sort_values("Disease").reset_index(drop=True)

    # Save summary stats
    stats_df.to_csv(STATS_CSV, index=False)

    # =========================
    # Plot: one image with all 8 diseases as a single horizontal boxplot chart
    # =========================
    plt.figure(figsize=(12, 8))
    ax = sns.boxplot(
        data=long_df,
        y="Disease",
        x="Rank",
        orient="h",
        showmeans=True,
        meanprops={"marker": "o", "markerfacecolor": "black", "markeredgecolor": "black", "markersize": 4},
        fliersize=2
    )

    # Optional: overlay median labels on each box (small, unobtrusive)
    medians = long_df.groupby("Disease")["Rank"].median()
    # Place median text near the median value on each row
    for ytick, disease in enumerate(medians.index):
        median_val = medians.loc[disease]
        ax.text(
            median_val, ytick,
            f"  median={int(median_val)}",
            va="center", ha="left", fontsize=8
        )

    ax.set_xlim(RANK_XMIN, RANK_XMAX)
    ax.set_xlabel("Rank")
    ax.set_ylabel("")
    ax.set_title("Distribution of Selected Gene Ranks across Diseases (Box-and-Whisker)")
    plt.tight_layout()

    # Save and close
    plt.savefig(PLOT_PATH, dpi=300)
    plt.close()

    # Console summary
    print(dedent(f"""
    Saved combined boxplots to: {PLOT_PATH}
    Saved summary stats to:     {STATS_CSV}
    """).strip())

    if skipped:
        print("\nNotes / Skipped datasets:")
        for d, why in skipped:
            print(f"- {d}: {why}")

if __name__ == "__main__":
    main()
