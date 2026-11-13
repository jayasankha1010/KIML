#!/bin/bash
# Build the GenePT literature matrix for the KIGNN-GENEPT arm.
#
# GenePT embeds each gene's NCBI Gene summary with text-embedding-ada-002
# (1,536 dims). The KIGNN-GENEPT run swaps it in for the MiniLM PubMed
# embeddings and keeps everything else of KI-GNN: AHBD expression features and
# the pathway + covaries knowledge graph.
#
# Two steps, both standard-library Python:
#   1. prepare_genept.py   stream the 3 GB CSV, keep the SPEOS genes (and the
#                          current names of genes SPEOS knows by an old symbol)
#   2. align_to_speos_symbols.py
#                          re-key to the SPEOS namespace, zero-fill the rest -
#                          the same step the TF-IDF and Doc2Vec arms went through
#
# Submitted rather than run on the login node because of the input size.
#
#   sbatch --account=punim2353 \
#       additional_experiments/text_representations/build_genept_features.slurm
#
#SBATCH --account=punim2353
#SBATCH --job-name=kiml_genept
#SBATCH --partition=sapphire
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
# The aligner holds the reduced matrix (~20k genes x 1,536) in memory as text,
# about 3 GB; 32G leaves plenty of room.
#SBATCH --mem=32G
#SBATCH --time=0-01:00:00
#SBATCH --output=logs/genept_%j.stdout
#SBATCH --error=logs/genept_%j.err
#SBATCH --mail-user=culuwitikega@student.unimelb.edu.au
#SBATCH --mail-type=FAIL,END

set -u

DIR=additional_experiments/text_representations
REDUCED="$DIR/genept_ada002_1536d.txt"
ALIGNED="$DIR/genept_ada002_1536d_speos_symbols.txt"

mkdir -p logs

echo "========================================"
echo " KIML: GenePT literature matrix"
echo "   started : $(date)"
echo "========================================"

module load Anaconda3/2022.10

python -u "$DIR/prepare_genept.py" -o "$REDUCED" || exit 1
python -u "$DIR/align_to_speos_symbols.py" --matrix "$REDUCED" -o "$ALIGNED" || exit 1

# The KI-GNN run reads this file blindly, so fail here if it is not the shape
# SPEOS expects: 17,282 rows, gene + 1,536 values each.
ROWS=$(wc -l < "$ALIGNED")
WIDTH=$(head -1 "$ALIGNED" | awk '{print NF}')
echo "--> $ALIGNED: $ROWS rows, $WIDTH fields per row"
if [ "$ROWS" -ne 17282 ] || [ "$WIDTH" -ne 1537 ]; then
    echo "[Error] expected 17282 rows of 1537 fields"
    exit 1
fi

echo "[Success] GenePT matrix ready at $(date)"
