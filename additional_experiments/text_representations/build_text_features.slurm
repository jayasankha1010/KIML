#!/bin/bash
# Build classical text representations for Reviewer 1 comments 4 and 5a.
#
# Three arms, so the comparison separates several things at once:
#   TF-IDF title only      what a paper's title alone carries
#   TF-IDF title+abstract  the full text the MiniLM embeddings were built from
#   Doc2Vec title+abstract a learned dense embedding, but trained only on the
#                          cutoff-restricted corpus - the middle ground between
#                          bag-of-words and a pretrained transformer
# against the existing MiniLM embeddings. If TF-IDF on title+abstract matches
# MiniLM, the signal is in the literature content rather than in contextual
# encoding. If title-only also matches, it is carried by very little text.
#
# Submitted rather than run on the login node: the input is ~1.2 GB and the
# TF-IDF matrix over ~19k genes x ~42 papers each is memory-hungry.
#
#   sbatch additional_experiments/text_representations/build_text_features.slurm
#
#SBATCH --account=punim0512
#SBATCH --job-name=kiml_text
#SBATCH --partition=sapphire
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
# TF-IDF over the full corpus is the memory peak, not the SVD. 64G is
# comfortable; drop --max-features if it is ever exceeded.
#SBATCH --mem=64G
# Doc2Vec over ~19k documents for 20 epochs is the long pole, not TF-IDF.
#SBATCH --time=0-06:00:00
#SBATCH --output=logs/text_%j.stdout
#SBATCH --error=logs/text_%j.err
#SBATCH --mail-user=culuwitikega@student.unimelb.edu.au
#SBATCH --mail-type=FAIL,END

set -u

PUBMED_DIR=/data/projects/punim2353/chathura/pubmed
# Unlabelled: title and abstract already concatenated. This is the file
# generate_pubmed_embeddings.py reads, so MiniLM was built from exactly this.
FULL_TEXT="$PUBMED_DIR/gene_details_2022_09.csv"
# Labelled 'Title: ... Abstract: ...'. Only this one allows the title-only arm.
LABELLED="$PUBMED_DIR/gene_paper_details_2022_09.csv"

SCRIPT=additional_experiments/text_representations/build_text_features.py
OUT_DIR=additional_experiments/text_representations
DIM=384   # matches MiniLM, so differences are attributable to the encoder

mkdir -p logs "$OUT_DIR"

echo "========================================"
echo " KIML: classical text representations"
echo "   started : $(date)"
echo "========================================"

module load Anaconda3/2022.10
module load web_proxy 2>/dev/null || echo "[info] web_proxy unavailable; continuing"

export CONDA_ENVS_PATH=/data/gpfs/projects/punim0512/anaconda3/envs
eval "$(conda shell.bash hook)"
conda activate speos_kiml || { echo "[Error] conda env speos_kiml not found"; exit 1; }

for f in "$FULL_TEXT" "$LABELLED"; do
    [ -f "$f" ] || { echo "[Error] missing input: $f"; exit 1; }
done

echo
echo "--> Inspecting both inputs"
python -u "$SCRIPT" --candidates "$FULL_TEXT" "$LABELLED" --inspect-only

echo
echo "--> Arm 1: title + abstract (same text MiniLM saw)"
SECONDS=0
python -u "$SCRIPT" --input "$FULL_TEXT" --text-scope full \
    --method tfidf_svd --dim "$DIM" \
    -o "$OUT_DIR/pubmed_tfidf_svd_full_${DIM}d_2022_09.txt"
ARM1=$?
echo "    finished in ${SECONDS}s (exit $ARM1)"

echo
echo "--> Arm 2: title only"
SECONDS=0
python -u "$SCRIPT" --input "$LABELLED" --text-scope title \
    --method tfidf_svd --dim "$DIM" \
    -o "$OUT_DIR/pubmed_tfidf_svd_title_${DIM}d_2022_09.txt"
ARM2=$?
echo "    finished in ${SECONDS}s (exit $ARM2)"

echo
echo "--> Arm 3: Doc2Vec on title + abstract"
# The third representation R1.4 names. Learned and dense like MiniLM, but
# trained only on the cutoff-restricted corpus, so it shares TF-IDF's property
# of carrying no pretraining that could hold post-cutoff information.
SECONDS=0
python -u "$SCRIPT" --input "$FULL_TEXT" --text-scope full \
    --method doc2vec --dim "$DIM" --epochs 20 \
    -o "$OUT_DIR/pubmed_doc2vec_full_${DIM}d_2022_09.txt"
ARM3=$?
echo "    finished in ${SECONDS}s (exit $ARM3)"

echo
echo "----------------------------------------"
if [ $ARM1 -eq 0 ] && [ $ARM2 -eq 0 ] && [ $ARM3 -eq 0 ]; then
    echo "[Success] all three arms built at $(date)"
    wc -l "$OUT_DIR"/pubmed_*_${DIM}d_2022_09.txt
    echo
    echo "Then re-key each to the SPEOS symbol namespace:"
    echo "  for f in $OUT_DIR/pubmed_*_${DIM}d_2022_09.txt; do"
    echo "    python additional_experiments/text_representations/align_to_speos_symbols.py --matrix \$f"
    echo "  done"
    echo
    echo "Next: point the model-class script at each matrix for a laptop-speed"
    echo "comparison across seven diseases, before committing any GPU time."
else
    echo "[Error] arm1 exit $ARM1, arm2 exit $ARM2, arm3 exit $ARM3"
    exit 1
fi
