#!/bin/bash
#SBATCH --account="punim0512"
#SBATCH --job-name="kiml_speos"
#SBATCH --partition=sapphire
#SBATCH --gres=gpu:0
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=1-12:00:00
#SBATCH --mail-user=culuwitikega@student.unimelb.edu.au
#SBATCH --mail-type=BEGIN,FAIL,END

echo "========================================"
echo " KIML: SPEOS Initialization & Execution"
echo "========================================"

# 1. Load required Spartan modules
echo "--> Loading standard HPC modules..."
module load Anaconda3/2022.10
module load CUDA/12.2.0
module load web_proxy

# 2. Force PIP and Linux to use the massive project drive for temporary downloads
export PIP_CACHE_DIR=/data/gpfs/projects/punim0512/pip_cache
export TMPDIR=/data/gpfs/projects/punim0512/pip_cache
mkdir -p $PIP_CACHE_DIR

# 3. Initialize Conda for the bash session
export CONDA_ENVS_PATH=/data/gpfs/projects/punim0512/anaconda3/envs
eval "$(conda shell.bash hook)"

# --- Configuration (Relative to KIML root) ---
ENV_NAME="speos_kiml"
REQ_FILE="external/SPEOS/requirements.yaml"

# 4. Check and Create Environment
echo ""
echo "--> Checking Conda dependencies..."
if conda info --envs | grep -E -q "\b$ENV_NAME\b"; then
    echo "[Info] Conda environment '$ENV_NAME' already exists."
else
    echo "[Info] Environment '$ENV_NAME' not found. Creating it natively..."
    echo "[Info] Note: This may take 10-15 minutes on the very first run."
    
    conda env create -n "$ENV_NAME" -f "$REQ_FILE"
    
    if [ $? -ne 0 ]; then
        echo "[Error] Failed to create the conda environment. Aborting job."
        exit 1
    fi
    echo "[Success] Environment created successfully."
fi

# 5. Activate the Environment
echo ""
echo "--> Activating environment: $ENV_NAME"
conda activate "$ENV_NAME"

# 6. Navigate to the execution directory
echo "--> Navigating to external/SPEOS..."
cd external/SPEOS || exit

# --- Configuration (Now relative to external/SPEOS/) ---
SCRIPT_PATH="outer_crossval.py"
CONFIG_PATH="configs/Exp_DEE_KIGNN.yaml"

# 7. Execute the Code
echo "--> Executing SPEOS cross-validation..."
echo "Running: python -u $SCRIPT_PATH -c $CONFIG_PATH"
echo "----------------------------------------"

python -u "$SCRIPT_PATH" -c "$CONFIG_PATH"

EXIT_CODE=$?

# 8. Cleanup and Exit
cd ../..
echo "----------------------------------------"
if [ $EXIT_CODE -eq 0 ]; then
    echo "[Success] SPEOS SLURM job completed execution."
else
    echo "[Error] SPEOS SLURM job encountered an error. Check the standard out/error logs."
    exit $EXIT_CODE
fi