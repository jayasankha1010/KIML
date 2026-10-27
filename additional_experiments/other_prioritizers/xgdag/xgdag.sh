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
conda activate "$ENV_NAME" || { echo "[Error] cannot activate '$ENV_NAME'"; exit 1; }
set -u

cd "$XGDAG_DIR" || exit 1
export PYTHONPATH="$PWD:$PWD/SubgraphX:$PWD/GraphSVX:${PYTHONPATH:-}"

echo "[info] env    : $ENV_NAME"
echo "[info] cwd    : $PWD"
echo "[info] running: python $*"
echo "----------------------------------------"
python "$@"
