#!/bin/bash
# Build the XGDAG environment WITHOUT asking conda to solve the whole stack.
#
# Solving pytorch 1.11 + pyg 2.0.4 + torch-scatter/sparse together is where
# conda stalls: those companion libraries are built against one exact torch
# build, so the solver explores a large space and often never converges. The
# classic solver can spin for an hour; mixing conda-forge with defaults (which
# a site .condarc usually adds) makes it worse.
#
# This avoids solving entirely:
#   1. conda installs python + torch only - a small, well-trodden solve
#   2. pip installs the PyG stack from data.pyg.org, whose wheels are indexed
#      BY torch version, so the right build is picked by URL rather than by
#      constraint satisfaction
#
# Deterministic, and it is the fallback the PyG project itself documents.
#
# Usage:
#   bash additional_experiments/other_prioritizers/xgdag/envs/setup_env.sh
#   ENV_NAME=xgdag_gpu CUDA=cu113 bash .../setup_env.sh    # GPU variant

set -euo pipefail

ENV_NAME="${ENV_NAME:-xgdag}"
TORCH_VERSION="${TORCH_VERSION:-1.11.0}"
CUDA="${CUDA:-cpu}"          # cpu | cu113
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"

echo "[+] env=$ENV_NAME  torch=$TORCH_VERSION  cuda=$CUDA  python=$PYTHON_VERSION"

# `set -u` must be OFF across every conda activation. Environments ship
# activate.d hooks that reference unset variables - this one has
# libblas_mkl_activate.sh, which reads MKL_INTERFACE_LAYER with no default and
# kills the script under nounset:
#     libblas_mkl_activate.sh: line 1: MKL_INTERFACE_LAYER: unbound variable
# (mantis-env has the same problem with JAVA_HOME.) The hooks are third-party,
# so guard the calls rather than patching them.
set +u
eval "$(conda shell.bash hook)"
set -u

# Resuming is the common case: the conda step succeeds, something later fails,
# and re-running should continue rather than refuse. Creation is the only part
# that is not idempotent, so skip just that.
if conda env list | grep -qE "^${ENV_NAME}[[:space:]]"; then
    echo "[=] environment '$ENV_NAME' already exists - skipping creation,"
    echo "    continuing with the pip steps (safe to repeat)."
    SKIP_CREATE=1
else
    SKIP_CREATE=0
fi

# Step 1 - python + torch only. Keep the solve small and prefer libmamba.
SOLVER=""
if conda config --show solver >/dev/null 2>&1; then
    SOLVER="--solver=libmamba"
fi

if [ "$SKIP_CREATE" -eq 0 ]; then
    echo "[+] creating environment with python and torch"
    if [ "$CUDA" = "cpu" ]; then
        conda create -y -n "$ENV_NAME" $SOLVER -c pytorch -c conda-forge \
            "python=${PYTHON_VERSION}" "pytorch=${TORCH_VERSION}" cpuonly
    else
        conda create -y -n "$ENV_NAME" $SOLVER -c pytorch -c conda-forge \
            "python=${PYTHON_VERSION}" "pytorch=${TORCH_VERSION}" \
            "cudatoolkit=${CUDA#cu}"
    fi
fi

set +u
conda activate "$ENV_NAME"
set -u

# Confirm torch is importable before anything tries to build against it.
python -c "import torch; print('[+] torch', torch.__version__)" || {
    echo "[Error] torch is not installed in '$ENV_NAME'."
    echo "        Remove the environment and let this script create it:"
    echo "          conda env remove -n $ENV_NAME"
    exit 1
}

# Step 2 - the PyG stack, from the index keyed by torch build. No solving.
#
# VERSIONS MUST BE PINNED and source builds forbidden. Unpinned, pip prefers
# the newest release it can see anywhere - so it picks torch-scatter 2.1.2
# from PyPI as a SOURCE tarball over the 2.0.9 wheel in this index, then tries
# to compile it. That build runs in an isolated environment with no torch, and
# dies with a misleading "ModuleNotFoundError: No module named 'torch'".
#
# --only-binary=:all: makes a missing wheel an immediate, honest error rather
# than a twenty-minute compile that fails at the end.
WHEELS="https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA}.html"
echo "[+] installing PyG stack from ${WHEELS}"
pip install --no-cache-dir --only-binary=:all: -f "$WHEELS" \
    "torch-scatter==2.0.9" "torch-sparse==0.6.14" "torch-cluster==1.6.0"
pip install --no-cache-dir "torch-geometric==2.0.4"

# Step 3 - the plain scientific stack. Versions matched to the authors' env.
echo "[+] installing remaining dependencies"
pip install --no-cache-dir \
    "networkx==2.7.1" "numpy==1.22.3" "pandas==1.4.4" \
    "scikit-learn==1.0.2" matplotlib seaborn tqdm

echo
echo "[+] verifying"
python "$(dirname "${BASH_SOURCE[0]}")/verify_env.py"
