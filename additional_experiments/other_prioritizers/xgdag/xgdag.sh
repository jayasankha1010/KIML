#!/bin/bash
# Run an XGDAG script with the paths and environment it needs.
#
# XGDAG cannot be run as shipped, for three reasons that are easy to hit one
# at a time and tedious to rediscover:
#
#   1. Paths.py uses RELATIVE paths ('Datasets/', 'Graphs/', 'Models/'), so
#      every script must run with the repo root as the working directory.
#   2. The vendored explainers use FLAT imports. SubgraphX/SubgraphX.py does
#      "from SubgraphXshapley import ..." and GraphSVX does "import
#      src.gengraph" / "from utils import featgen", with no __init__.py to
#      make either work as a package. Both directories have to be on
#      PYTHONPATH in their own right.
#   3. GDARanking.py imports SubgraphX unconditionally, so even the cheap
#      gnnexplainer path needs rdkit - a cheminformatics library that appears
#      in none of the four shipped CondaEnvs files.
#
# Usage:
#   bash xgdag.sh ComputeRankingScript.py C0009402 gnnexplainer 4
#   bash xgdag.sh CreateGraph.py
#   XGDAG_DIR=/path/to/XGDAG bash xgdag.sh TrainerScript.py

set -uo pipefail

XGDAG_DIR="${XGDAG_DIR:-/data/gpfs/projects/punim2353/chathura/tools/XGDAG}"
ENV_NAME="${XGDAG_ENV:-xgdag}"

if [ "$#" -lt 1 ]; then
    echo "usage: xgdag.sh <script.py> [args...]"
    echo "  e.g. xgdag.sh ComputeRankingScript.py C0009402 gnnexplainer 4"
    exit 1
fi

[ -d "$XGDAG_DIR" ] || { echo "[Error] XGDAG not found at $XGDAG_DIR"; exit 1; }

# set -u off across conda activation: activate.d hooks reference unset
# variables (MKL_INTERFACE_LAYER here, JAVA_HOME in mantis-env) and abort the
# script under nounset.
set +u
eval "$(conda shell.bash hook)"
# XGDAG_ENV may be a NAME or a full PREFIX PATH. Environments with CUDA
# PyTorch are several GB and will blow a home-directory quota, so they often
# have to live under the project allocation and be activated by path.
conda activate "$ENV_NAME" || { echo "[Error] cannot activate '$ENV_NAME'"; exit 1; }
set -u

# torch-sparse and torch-cluster are compiled against CUDA and link to
# libcusparse.so.11 / libcublas.so.11. The torch +cu113 pip wheel ships those
# inside torch/lib/, but the dynamic loader does not look there by default, so
# importing torch_geometric fails with
#     OSError: libcusparse.so.11: cannot open shared object file
# even though the library is present. Point LD_LIBRARY_PATH at it. Harmless
# for the CPU environment, where the directory simply holds no CUDA libs.
TORCH_LIB=$(python -c "import os,torch;print(os.path.join(os.path.dirname(torch.__file__),'lib'))" 2>/dev/null)
if [ -n "${TORCH_LIB:-}" ] && [ -d "$TORCH_LIB" ]; then
    export LD_LIBRARY_PATH="${TORCH_LIB}:${LD_LIBRARY_PATH:-}"
    echo "[info] torch libs: ${TORCH_LIB}"
fi

cd "$XGDAG_DIR" || exit 1
export PYTHONPATH="$PWD:$PWD/SubgraphX:$PWD/GraphSVX:${PYTHONPATH:-}"

echo "[info] env    : $ENV_NAME"
echo "[info] cwd    : $PWD"
echo "[info] running: python $*"
echo "----------------------------------------"
python "$@"
