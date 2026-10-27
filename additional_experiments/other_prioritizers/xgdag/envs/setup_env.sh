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

eval "$(conda shell.bash hook)"

if conda env list | grep -qE "^${ENV_NAME}\s"; then
    echo "[!] environment '$ENV_NAME' already exists."
    echo "    Remove it first:  conda env remove -n $ENV_NAME"
    exit 1
fi

# Step 1 - python + torch only. Keep the solve small and prefer libmamba.
SOLVER=""
if conda config --show solver >/dev/null 2>&1; then
    SOLVER="--solver=libmamba"
fi

echo "[+] creating environment with python and torch"
if [ "$CUDA" = "cpu" ]; then
    conda create -y -n "$ENV_NAME" $SOLVER -c pytorch -c conda-forge \
        "python=${PYTHON_VERSION}" "pytorch=${TORCH_VERSION}" cpuonly
else
    conda create -y -n "$ENV_NAME" $SOLVER -c pytorch -c conda-forge \
        "python=${PYTHON_VERSION}" "pytorch=${TORCH_VERSION}" \
        "cudatoolkit=${CUDA#cu}"
fi

conda activate "$ENV_NAME"

# Step 2 - the PyG stack, from the index keyed by torch build. No solving.
WHEELS="https://data.pyg.org/whl/torch-${TORCH_VERSION}+${CUDA}.html"
echo "[+] installing PyG stack from ${WHEELS}"
pip install --no-cache-dir torch-scatter torch-sparse torch-cluster -f "$WHEELS"
pip install --no-cache-dir "torch-geometric==2.0.4"

# Step 3 - the plain scientific stack. Versions matched to the authors' env.
echo "[+] installing remaining dependencies"
pip install --no-cache-dir \
    "networkx==2.7.1" "numpy==1.22.3" "pandas==1.4.4" \
    "scikit-learn==1.0.2" matplotlib seaborn tqdm

echo
echo "[+] verifying"
python "$(dirname "${BASH_SOURCE[0]}")/verify_env.py"
