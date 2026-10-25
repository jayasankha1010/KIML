#!/bin/bash
# Mantis/RF seed runs - the RF half of the main-table confidence intervals.
#
# Mirrors run_revision.slurm for the GNN arm: one manifest line per job, index
# selected by SLURM_ARRAY_TASK_ID, portable scratch, loud early failures.
#
# Manifest lines are  <disease>:<arm>:<seed>  e.g.  dee:RF:1
# Generate it with make_mantis_manifest.py.
#
# WHAT CHANGED IN MANTIS TO MAKE THIS POSSIBLE
#   --feature-mode  the three arms were hardcoded literals in
#                   feature_table_compiler.py, so producing RF / C-RF / KI-RF
#                   meant editing source between runs.
#   --seed          cfg.random_state looked like it controlled randomness, but
#                   balanced_datasets_random_generator.py drew its positive
#                   subsample and fold seeds from an unseeded global RNG.
#
# CLASSIFIER: -m rf. The published runs used -m xgb (see main_*.nf and the
# archived slurm logs) even though the manuscript labels the arm Random
# Forest. These runs use actual Random Forest, so they will NOT reproduce the
# published numbers exactly - that is intended and needs stating in the paper.
#
# Usage:
#   sbatch --account=punim2353 --array=0 run_mantis.slurm          # one timed run
#   sbatch --account=punim2353 --array=0-134%4 run_mantis.slurm    # the lot
#
#SBATCH --account=punim2353
#SBATCH --job-name=kiml_mantis
#SBATCH --output=logs/mantis_%A_%a.stdout
#SBATCH --error=logs/mantis_%A_%a.err
#SBATCH --time=0-08:00:00
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G

set -u

# Mantis does NOT share the SPEOS environment. setup.py pins tensorflow 1.13.1
# and Keras 2.2.4, and ensemble_lib.py does `from keras.optimizers import Adam`
# at import time, so the PyTorch env used for SPEOS cannot run it. Set
# MANTIS_ENV to whichever environment the original Mantis runs used:
#   MANTIS_ENV=mantis sbatch ... run_mantis.slurm
ENV_NAME="${MANTIS_ENV:-speos_kiml}"
MANIFEST=additional_experiments/revision_runs/mantis_manifest.txt
NTHREADS="${SLURM_CPUS_PER_TASK:-16}"
ITERATIONS=1          # matches the published runs (-i 1)
MODEL=rf              # Random Forest, per the decision above

# Lookups use `case`, not associative arrays. `declare -A` needs bash 4, and
# where it is unavailable it fails SILENTLY: the array degrades to an indexed
# one, every string subscript evaluates to 0, and all three arms resolve to
# whichever was declared last. That would run the entire study as one arm with
# no error. `case` works on any POSIX shell.
stem_for() {
    case "$1" in
        dee)                     echo dee_2022 ;;
        ad_dee)                  echo dee_2022_ad ;;
        ar_dee)                  echo dee_2022_ar ;;
        microcephaly)            echo other_microcephaly ;;
        intellectual_disability) echo other_intellectual_disability ;;
        mnd)                     echo other_mnd ;;
        cp)                      echo other_cp ;;
        platelet_disorder)       echo other_platelet_disorder ;;
        arthrogryposis)          echo other_arthrogryposis ;;
        *)                       echo "" ;;
    esac
}
feature_mode_for() {
    case "$1" in
        RF)    echo core_only ;;
        C-RF)  echo external_only ;;
        KI-RF) echo combined ;;
        *)     echo "" ;;
    esac
}

if [ ! -f "$MANIFEST" ]; then
    echo "[Error] Manifest not found: $MANIFEST"
    echo "        Generate it with make_mantis_manifest.py"
    exit 1
fi

LINE=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "$MANIFEST")
if [ -z "$LINE" ]; then
    echo "[Error] No manifest entry at index ${SLURM_ARRAY_TASK_ID}"
    echo "        Manifest has $(wc -l < "$MANIFEST") lines (indices 0-$(( $(wc -l < "$MANIFEST") - 1 )))"
    exit 1
fi

DISEASE="${LINE%%:*}"
REST="${LINE#*:}"
ARM="${REST%%:*}"
SEED="${REST##*:}"

STEM=$(stem_for "$DISEASE")
FMODE=$(feature_mode_for "$ARM")
if [ -z "$STEM" ]; then
    echo "[Error] Unknown disease '$DISEASE' in manifest line '$LINE'"
    exit 1
fi
if [ -z "$FMODE" ]; then
    echo "[Error] Unknown arm '$ARM' in manifest line '$LINE'"
    exit 1
fi

RUN_NAME="Mantis_${DISEASE}_${ARM}_s${SEED}"
echo "----------------------------------------"
echo "index      : ${SLURM_ARRAY_TASK_ID}"
echo "run        : ${RUN_NAME}"
echo "disease    : ${DISEASE}"
echo "arm        : ${ARM}  (--feature-mode ${FMODE})"
echo "seed       : ${SEED}"
echo "classifier : ${MODEL}"
echo "threads    : ${NTHREADS}"
echo "started    : $(date)"
echo "----------------------------------------"

# Scratch beside the checkout, not at a hardcoded project path - so moving the
# repository between allocations does not leave temp files on the old, full
# filesystem. Same reasoning as run_revision.slurm.
KIML_ROOT="${SLURM_SUBMIT_DIR:-$PWD}"
: "${KIML_SCRATCH:=${KIML_ROOT}/.scratch}"
export PIP_CACHE_DIR="${KIML_SCRATCH}/pip_cache"
export TMPDIR="${KIML_SCRATCH}/tmp"
mkdir -p "$PIP_CACHE_DIR" "$TMPDIR" || {
    echo "[Error] Cannot create scratch under ${KIML_SCRATCH}. Check quota:"
    echo "          check_project_usage"
    exit 1
}
echo "[info] scratch: ${KIML_SCRATCH}"

# Deliberately NOT setting CONDA_ENVS_PATH here. run_revision.slurm points it
# at the shared SPEOS envs under punim0512, but mantis-env lives in the user's
# home anaconda install - overriding the search path can hide it.
# `set -u` must be OFF across conda activation. Environments can ship
# activate.d hooks that reference unset variables - mantis-env has
# openjdk_activate.sh, which reads JAVA_HOME with no default and aborts the
# job under nounset with:
#     openjdk_activate.sh: line 1: JAVA_HOME: unbound variable
# The hooks are third-party, so guard the call rather than patching them.
set +u
eval "$(conda shell.bash hook)"
if ! conda info --envs | grep -E -q "(^|/)${ENV_NAME}[[:space:]]"; then
    echo "[Error] Conda environment '$ENV_NAME' not found. Available:"
    conda info --envs | sed 's/^/          /'
    echo "        Set MANTIS_ENV=<name> when submitting."
    exit 1
fi
conda activate "$ENV_NAME" || {
    echo "[Error] Could not activate '$ENV_NAME'."
    exit 1
}
set -u
echo "[info] environment: ${ENV_NAME}  ($(python -c 'import sys; print(sys.version.split()[0])'))"

cd external/Mantis || exit 1

# `python path/to/__main__.py` puts the SCRIPT's directory on sys.path, not the
# working directory, so `import mantis_ml` fails with ModuleNotFoundError even
# when standing in external/Mantis. The original Nextflow runs worked because
# the package was pip-installed in their environment. Putting the package root
# on PYTHONPATH avoids needing to install it.
export PYTHONPATH="$PWD:${PYTHONPATH:-}"

# Fail now, with a readable message, rather than part-way through a long run.
python - <<'PREFLIGHT' || exit 1
import importlib, sys
missing = []
for mod in ("mantis_ml", "sklearn", "pandas", "numpy", "yaml", "keras"):
    try:
        importlib.import_module(mod)
    except Exception as exc:
        missing.append("{}: {}".format(mod, exc))
if missing:
    print("[Error] Mantis dependencies unavailable in this environment:")
    for m in missing:
        print("   " + m)
    print("")
    print("        Mantis needs its own environment - setup.py pins")
    print("        tensorflow 1.13.1 / Keras 2.2.4, which the SPEOS env lacks.")
    print("        Find the environment the original Mantis runs used:")
    print("          conda env list")
    print("        then resubmit with:  MANTIS_ENV=<name> sbatch ...")
    sys.exit(1)
print("[info] preflight: mantis_ml and dependencies import cleanly")
PREFLIGHT

CONFIG="mantis_ml/conf/${STEM}_config.yaml"
KNOWN="Input_Files/${STEM}.tsv"
OUTDIR="Mantis_Out/${RUN_NAME}"

for f in "$CONFIG" "$KNOWN"; do
    if [ ! -f "$f" ]; then
        echo "[Error] Missing input: external/Mantis/$f"
        exit 1
    fi
done
mkdir -p "$OUTDIR"

START=$(date +%s)
env python mantis_ml/modules/main/__main__.py \
    -n "$NTHREADS" \
    -i "$ITERATIONS" \
    -m "$MODEL" \
    -o "$OUTDIR" \
    -c "$CONFIG" \
    -k "$KNOWN" \
    --feature-mode "$FMODE" \
    --seed "$SEED"
STATUS=$?
ELAPSED=$(( $(date +%s) - START ))

echo "----------------------------------------"
echo "--> Mantis finished in ${ELAPSED}s (exit ${STATUS})"
if [ "$STATUS" -ne 0 ]; then
    echo "[Error] ${RUN_NAME} failed."
    exit "$STATUS"
fi
echo "[Success] ${RUN_NAME} complete at $(date) (${ELAPSED}s total)"
echo "[info] outputs under external/Mantis/${OUTDIR}"
