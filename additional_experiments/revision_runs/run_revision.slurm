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
# 2. Run ONE task and check both wall-clock and reproduction. Pick the index of
#    the DEE KI-GNN config, which is the one with a well-known published value.
#    With the default 9 diseases x 3 variants x 5 seeds the manifest is ordered
#    disease (alphabetical) -> variant (GNN, CGNN, KIGNN) -> seed, so:
#
#        grep -n '^Rev_dee_KIGNN_s1$' external/SPEOS/revision_manifest.txt
#        # -> line 71, i.e. array index 70
#        sbatch --array=70 additional_experiments/revision_runs/run_revision.slurm
#
#    Do NOT use --array=0 for this check: index 0 is Rev_ad_dee_GNN_s1, a
#    different disease and configuration.
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
# Comma-separated list: SLURM schedules on whichever becomes free first, which
# matters more than peak FLOPs here. The model is tiny (17k nodes, dim 50, ~3.5
# MB of activations), so any of these is ample and availability dominates.
#SBATCH --partition=gpu-a100,gpu-h100,gpu-l40s
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
# Measured on CPU: ~55 s/epoch, ~193 min/fold, 30 folds => ~96 h per config.
# At the ~8x GPU speedup implied by prior experience (~24 min/fold) that is
# ~12 h, so 24 h leaves headroom. Reduce if the partition caps walltime.
#SBATCH --time=1-00:00:00
# .stdout rather than .out: the repo's .gitignore has a bare "*.out", so stdout
# logs would be silently unshareable.
#SBATCH --output=logs/rev_%A_%a.stdout
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
# Not present on every Spartan partition, and only needed for outbound network
# access, which these runs do not use. Tolerate its absence instead of spraying
# an Lmod error over the log.
module load web_proxy 2>/dev/null || echo "[info] web_proxy module unavailable; continuing"

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

# Confirm a GPU was actually allocated. SPEOS has cuda: auto, so a failed or
# absent allocation does not error - it silently falls back to CPU and the job
# then takes ~8x longer and dies on the walltime.
echo "--> GPU check:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null \
    || echo "    [WARNING] nvidia-smi unavailable - this job will run on CPU"
python -c "import torch; print('    torch.cuda.is_available():', torch.cuda.is_available())"

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
