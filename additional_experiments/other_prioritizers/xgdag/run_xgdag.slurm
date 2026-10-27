#!/bin/bash
# Run an XGDAG script as a batch job.
#
# The reproduction gate and the later DEE runs both take long enough that a
# login-node session is the wrong place for them - a dropped VS Code or SSH
# connection kills the process and the work is lost. Batch jobs survive
# disconnection; interactive ones do not.
#
# Wraps xgdag.sh, so the environment activation, working directory and
# PYTHONPATH handling are identical to running it by hand.
#
# Usage:
#   sbatch run_xgdag.slurm ComputeRankingScript.py C0009402 gnnexplainer 4
#   sbatch run_xgdag.slurm CreateGraph.py
#   sbatch run_xgdag.slurm TrainerScript.py
#
#SBATCH --account=punim2353
#SBATCH --job-name=xgdag
#SBATCH --output=logs/xgdag_%j.out
#SBATCH --error=logs/xgdag_%j.err
#SBATCH --time=0-06:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G

set -uo pipefail

KIML="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$KIML" || exit 1

if [ "$#" -lt 1 ]; then
    echo "[Error] usage: sbatch run_xgdag.slurm <script.py> [args...]"
    exit 1
fi

echo "----------------------------------------"
echo "script  : $*"
echo "cpus    : ${SLURM_CPUS_PER_TASK:-?}"
echo "started : $(date)"
echo "----------------------------------------"

START=$(date +%s)
bash additional_experiments/other_prioritizers/xgdag/xgdag.sh "$@"
STATUS=$?
ELAPSED=$(( $(date +%s) - START ))

echo "----------------------------------------"
echo "--> finished in ${ELAPSED}s (exit ${STATUS})"

# ComputeRankingScript writes into XGDAG's own Rankings/ directory, so show
# what changed rather than making the reader go looking.
XGDAG_DIR="${XGDAG_DIR:-/data/gpfs/projects/punim2353/chathura/tools/XGDAG}"
if [ -d "$XGDAG_DIR/Rankings" ]; then
    echo "[info] rankings modified in the last hour:"
    find "$XGDAG_DIR/Rankings" -type f -mmin -60 -printf '   %TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | head -20
fi

if [ "$STATUS" -ne 0 ]; then
    echo "[Error] XGDAG run failed."
    exit "$STATUS"
fi
echo "[Success] complete at $(date)"
