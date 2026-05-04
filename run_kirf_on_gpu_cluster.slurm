#!/bin/bash
#SBATCH --account="punim2453"
#SBATCH --job-name="dee_2022"
#SBATCH --partition=sapphire
#SBATCH --gres=gpu:0
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=512G
#SBATCH --time=0-8:0:00
#SBATCH --mail-user=culuwitikega@student.unimelb.edu.au
#SBATCH --mail-type=BEGIN,FAIL,END

echo "========================================"
echo " KIML: Mantis Initialization & Execution"
echo "========================================"

# 1. Load required Spartan modules
echo "--> Loading standard HPC modules..."
module purge
module load Anaconda3/2022.10
module load web_proxy

# 2. Force PIP and Linux to use the massive project drive for temporary downloads
export PIP_CACHE_DIR=/data/gpfs/projects/punim2453/pip_cache
export TMPDIR=/data/gpfs/projects/punim2453/pip_cache
mkdir -p $PIP_CACHE_DIR

# 3. Initialize Conda for the bash session
export CONDA_ENVS_PATH=/data/gpfs/projects/punim2453/anaconda3/envs
eval "$(conda shell.bash hook)"

# --- Configuration ---
ENV_NAME="mantis_kiml"

# 4. Check, Create, and Activate Environment
echo ""
echo "--> Checking Conda dependencies..."
if conda info --envs | grep -E -q "\b$ENV_NAME\b"; then
    echo "[Info] Conda environment '$ENV_NAME' already exists."
    
    # Activate and navigate
    conda activate "$ENV_NAME"
    cd external/Mantis || exit
else
    echo "[Info] Environment '$ENV_NAME' not found."
    echo "[Info] Creating base Python 3.7 environment..."
    
    conda create -n "$ENV_NAME" python=3.7 pip -y
    
    if [ $? -ne 0 ]; then
        echo "[Error] Failed to create the base conda environment. Aborting job."
        exit 1
    fi
    
    echo "[Success] Base environment created. Activating..."
    conda activate "$ENV_NAME"
    
    cd external/Mantis || exit
    
    echo "--> Installing Mantis dependencies via setup.py..."
    pip install -e .
    
    if [ $? -ne 0 ]; then
        echo "[Error] Failed to install dependencies via setup.py. Aborting job."
        exit 1
    fi
    echo "[Success] Mantis installed successfully."
fi

# 5. Force the prefix to prioritize the environment's binaries
export PATH="$CONDA_PREFIX/bin:$PATH"

# 5b. Ensure Legacy Nextflow is installed (Mantis requires DSL1 syntax)
if ! command -v nextflow &> /dev/null || ! nextflow -v | grep -q "version 21"; then
    echo "--> Installing legacy Nextflow (v21.10.6) for Mantis compatibility..."
    conda install -c bioconda "nextflow=21.10.6" -y
fi

# 5c. Patch Broken Dependencies for Legacy Python 3.7 Packages
echo "--> Verifying legacy dependencies..."
PROTOBUF_VERSION=$(pip show protobuf | grep Version | awk '{print $2}')
if [[ $PROTOBUF_VERSION == 4.* ]]; then
    echo "--> Patching Protobuf: Downgrading v$PROTOBUF_VERSION to v3.20.3 for TF 1.13 compatibility..."
    pip install "protobuf<3.20.4"
fi

JINJA_VERSION=$(pip show Jinja2 | grep Version | awk '{print $2}')
if [[ "$JINJA_VERSION" > "3.0.9" ]]; then
    echo "--> Patching Jinja2: Downgrading v$JINJA_VERSION to v3.0.3 for Bokeh 1.1.0 compatibility..."
    pip install "Jinja2<3.1.0"
fi

echo "----------------------------------------"
echo "which python → $(which python)"
echo "python version → $(python --version)"
echo "which nextflow → $(which nextflow)"
echo "nextflow version → $(nextflow -v)"
echo "----------------------------------------"

# 6. Execute the Nextflow Pipeline
echo "--> Executing Mantis Nextflow pipeline..."
echo "Running: nextflow run main_dee_2022.nf"
echo "----------------------------------------"

nextflow run main_dee_2022.nf

EXIT_CODE=$?

# 7. Cleanup and Exit
cd ../..
echo "----------------------------------------"

# --- AUTOMATED EVALUATION STEP (Runs unconditionally) ---
echo "--> Attempting Evaluation Metrics..."
python results/evaluate_mantis_single.py \
  --name "$EXP_NAME" \
  --folder "dee_2022_dee_2022_pubmed_only_1_iter_custom" \
  --targets "DEE-2025_03_vs_2022_09.txt" \
  --metrics_out "RF_results/rank_metrics.tsv"

echo "----------------------------------------"

# 8. Final Status Check
if [ $EXIT_CODE -eq 0 ]; then
    echo "[Success] Mantis pipeline and evaluation completed successfully."
else
    echo "[Error] Mantis pipeline encountered an error upstream. Check the Nextflow logs."
    exit $EXIT_CODE
fi