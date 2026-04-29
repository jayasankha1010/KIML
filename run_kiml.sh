#!/bin/bash

echo "========================================"
echo " KIML: SPEOS Initialization & Execution"
echo " (Generic Linux Version)"
echo "========================================"

# 1. Initialize Conda for the bash session
# This automatically finds where Anaconda/Miniconda is installed on the Linux system
CONDA_BASE=$(conda info --base)
source "$CONDA_BASE/etc/profile.d/conda.sh"

# --- Configuration (Relative to KIML root) ---
ENV_NAME="speos_kiml"
REQ_FILE="external/SPEOS/requirements.yaml"

# --- Experiment Variables ---
EXP_NAME="Exp_DEE_KIGNN"
DATASET="dee"

# 2. Check and Create Environment
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

# 3. Activate the Environment
echo ""
echo "--> Activating environment: $ENV_NAME"
conda activate "$ENV_NAME"

# 4. Navigate to the execution directory
echo "--> Navigating to external/SPEOS..."
cd external/SPEOS || exit

# --- Configuration (Now relative to external/SPEOS/) ---
SCRIPT_PATH="outer_crossval.py"
CONFIG_PATH="configs/${EXP_NAME}.yaml"

# 5. Execute the Main Pipeline
echo "--> Executing SPEOS cross-validation..."
echo "Running: python -u $SCRIPT_PATH -c $CONFIG_PATH"
echo "----------------------------------------"

python -u "$SCRIPT_PATH" -c "$CONFIG_PATH"
MAIN_EXIT_CODE=$?

# 6. Execute Post-Processing (Only if main pipeline succeeds)
echo "----------------------------------------"
if [ $MAIN_EXIT_CODE -eq 0 ]; then
    echo "[Success] Main SPEOS pipeline completed. Starting post-processing..."
    
    # Step 6a: Summarize Probabilities
    echo "--> Summarizing output probabilities..."
    python -u ./results_processing/summarize_output_probabilities.py -e "$EXP_NAME"
    SUM_EXIT_CODE=$?
    
    # Step 6b: Evaluate Results (Only if summarization succeeds)
    if [ $SUM_EXIT_CODE -eq 0 ]; then
        echo "--> Evaluating results..."
        python -u ./results_processing/evaluate_results.py -e "$EXP_NAME" -d "$DATASET" --comment "$EXP_NAME"
        FINAL_EXIT_CODE=$?
    else
        echo "[Error] Probability summarization failed. Skipping evaluation."
        FINAL_EXIT_CODE=$SUM_EXIT_CODE
    fi
else
    echo "[Error] Main SPEOS pipeline failed. Skipping all post-processing."
    FINAL_EXIT_CODE=$MAIN_EXIT_CODE
fi

# 7. Cleanup and Exit
cd ../..
echo "----------------------------------------"
if [ $FINAL_EXIT_CODE -eq 0 ]; then
    echo "[Success] Entire KIML Pipeline (Training + Evaluation) completed flawlessly."
else
    echo "[Error] KIML Pipeline encountered an error."
    exit $FINAL_EXIT_CODE
fi