#!/bin/bash
# SLURM array for the Bioinformatics Advances revision runs.
#
# One array task = one SPEOS outer-crossvalidation run = one line of
# external/SPEOS/revision_manifest.txt (disease x variant x seed).
#
# BEFORE SUBMITTING THE FULL ARRAY
# --------------------------------
# 1. Generate the configs:
#        python additional_experiments/revision_runs/make_configs.py --seeds 5
#
# 2. Run ONE task and check both wall-clock and reproduction:
#        sbatch --array=0 additional_experiments/revision_runs/run_revision.slurm
#
#    The DEE KI-GNN median rank published in Table 1 is 1379. SPEOS does not
#    call torch.manual_seed anywhere, so an exact match is not expected; what
#    matters is that the value lands in the same neighbourhood. A result far
#    from it means this repo is not configured the way the paper's runs were,
#    and the whole array would produce numbers that contradict the manuscript.
#
# 3. Set --time and --array accordingly, then submit the rest.
#
#SBATCH --account=punim0512
#SBATCH --job-name=kiml_rev
#SBATCH --partition=sapphire
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=0-08:00:00
#SBATCH --output=logs/rev_%A_%a.out
#SBATCH --error=logs/rev_%A_%a.err
#SBATCH --mail-user=culuwitikega@student.unimelb.edu.au
#SBATCH --mail-type=FAIL,END

set -u

MANIFEST="external/SPEOS/revision_manifest.txt"
ENV_NAME="speos_kiml"

mkdir -p logs

if [ ! -f "$MANIFEST" ]; then
    echo "[Error] $MANIFEST not found. Run make_configs.py first."
    exit 1
fi

# Array index -> config name. Index is 0-based, sed is 1-based.
EXP_NAME=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$MANIFEST")
if [ -z "$EXP_NAME" ]; then
    echo "[Error] No manifest entry for array index $SLURM_ARRAY_TASK_ID."
    exit 1
fi

# Config name encodes the disease, which evaluate_results.py needs separately.
# Rev_<disease>_<variant>_s<seed>  ->  <disease>
DATASET=$(echo "$EXP_NAME" | sed -E 's/^Rev_(.+)_[A-Za-z-]+_s[0-9]+$/\1/')

echo "========================================"
echo " KIML revision run"
echo "   array task : ${SLURM_ARRAY_TASK_ID}"
echo "   config     : ${EXP_NAME}"
echo "   disease    : ${DATASET}"
echo "   started    : $(date)"
echo "========================================"

module load Anaconda3/2022.10
module load CUDA/12.2.0
module load web_proxy

export PIP_CACHE_DIR=/data/gpfs/projects/punim0512/pip_cache
export TMPDIR=/data/gpfs/projects/punim0512/pip_cache
mkdir -p "$PIP_CACHE_DIR"

export CONDA_ENVS_PATH=/data/gpfs/projects/punim0512/anaconda3/envs
eval "$(conda shell.bash hook)"

if ! conda info --envs | grep -E -q "\b$ENV_NAME\b"; then
    echo "[Error] Conda environment '$ENV_NAME' not found."
    echo "        Create it once interactively before submitting the array:"
    echo "          conda env create -n $ENV_NAME -f external/SPEOS/requirements.yaml"
    exit 1
fi
conda activate "$ENV_NAME"

cd external/SPEOS || exit 1

CONFIG_PATH="configs/${EXP_NAME}.yaml"
if [ ! -f "$CONFIG_PATH" ]; then
    echo "[Error] $CONFIG_PATH not found. Re-run make_configs.py."
    exit 1
fi

echo "--> Training: python -u outer_crossval.py -c $CONFIG_PATH"
SECONDS=0
python -u outer_crossval.py -c "$CONFIG_PATH"
TRAIN_EXIT=$?
echo "--> Training finished in ${SECONDS}s (exit ${TRAIN_EXIT})"

if [ $TRAIN_EXIT -ne 0 ]; then
    echo "[Error] Training failed; skipping post-processing."
    exit $TRAIN_EXIT
fi

echo "--> Summarising probabilities..."
python -u ./results_processing/summarize_output_probabilities.py -e "$EXP_NAME" || exit 1

# Per-run metrics are appended to a per-task file so concurrent array tasks do
# not interleave writes into one shared TSV. Concatenate them afterwards with:
#   head -1 rank_metrics_Rev_*.tsv | head -1 > rank_metrics_revision.tsv
#   tail -q -n +2 rank_metrics_Rev_*.tsv >> rank_metrics_revision.tsv
echo "--> Evaluating..."
python -u ./results_processing/evaluate_results.py \
    -e "$EXP_NAME" \
    -d "$DATASET" \
    --comment "$EXP_NAME" \
    --summary "rank_metrics_${EXP_NAME}.tsv" || exit 1

cd ../..
echo "----------------------------------------"
echo "[Success] ${EXP_NAME} complete at $(date) (${SECONDS}s total)"
