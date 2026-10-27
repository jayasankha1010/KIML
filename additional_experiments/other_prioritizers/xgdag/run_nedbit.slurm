#!/bin/bash
# NeDBIT feature generation for XGDAG - step 1 of the external-comparator
# comparison (R1.8 / R3.2).
#
# CPU only: Perl plus a C binary. No GPU, no conda environment. The heavy
# dependencies (PyTorch 1.12 / PyG 2.1) are needed later, for XGDAG's GNN and
# explainer stages, not here.
#
# The calculator iterates once per gene over a ~19,761-node BioGRID graph and
# prints "<i> su 19761" for each, so it is slow and extremely verbose. An
# interactive session is the wrong place for it; the progress lines are
# thinned below so the log stays readable.
#
# Usage:
#   sbatch additional_experiments/other_prioritizers/xgdag/run_nedbit.slurm dee
#   sbatch .../run_nedbit.slurm                 # all nine diseases, serially
#
#SBATCH --account=punim2353
#SBATCH --job-name=nedbit
#SBATCH --output=logs/nedbit_%j.out
#SBATCH --error=logs/nedbit_%j.err
#SBATCH --time=0-08:00:00
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G

set -uo pipefail

NIAPU="${NIAPU_DIR:-/data/gpfs/projects/punim2353/chathura/tools/NIAPU}"
KIML="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$KIML" || exit 1

echo "----------------------------------------"
echo "NIAPU      : $NIAPU"
echo "working dir: $KIML"
echo "diseases   : ${*:-<all>}"
echo "started    : $(date)"
echo "----------------------------------------"

if [ ! -d "$NIAPU" ]; then
    echo "[Error] NIAPU not found at $NIAPU"
    echo "        git clone https://github.com/AndMastro/NIAPU.git into tools/,"
    echo "        or set NIAPU_DIR when submitting."
    exit 1
fi

START=$(date +%s)

# Thin the per-gene progress spam: keep anything that is not a progress line
# (warnings, errors, the header echo) plus every 500th progress line, so the
# log shows movement without carrying ~20k lines per pass.
bash additional_experiments/other_prioritizers/xgdag/run_nedbit.sh "$NIAPU" "$@" 2>&1 \
    | awk '!/ su [0-9]+$/ { print; next } NR % 500 == 0 { print }'

STATUS=${PIPESTATUS[0]}
ELAPSED=$(( $(date +%s) - START ))
echo "----------------------------------------"
echo "--> finished in ${ELAPSED}s (exit ${STATUS})"

OUT="additional_experiments/other_prioritizers/xgdag/features"
if [ -d "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
    echo "[info] feature files:"
    for f in "$OUT"/*_features; do
        [ -f "$f" ] || continue
        echo "   $(basename "$f"): $(( $(wc -l < "$f") - 1 )) genes"
        echo "      md5 $(md5sum "$f" | cut -d' ' -f1)"
    done
    # The calculator prints a seed line ONLY when FIXEDSEED is undefined. If
    # one appears, the run was stochastic - cutSeedGenes() drops a random
    # subset of seed genes - and the features are not reproducible.
    echo "[info] reproducibility: no 'SEME' line above means FIXEDSEED took effect"
fi

if [ "$STATUS" -ne 0 ]; then
    echo "[Error] NeDBIT generation failed."
    exit "$STATUS"
fi
echo "[Success] complete at $(date)"
