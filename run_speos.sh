#!/bin/bash
# test_speos.sh

ENV_NAME="kiml_speos"
REQ_FILE="external/SPEOS/requirements.yaml"

# Notice these paths are now relative to the SPEOS folder, because we will cd into it
SCRIPT_PATH="outer_crossval.py"
CONFIG_PATH="configs/Exp_DEE_KIGNN.yaml"

echo "========================================"
echo " Initializing SPEOS Framework Test"
echo "========================================"

# 1. Explicitly initialize Conda for this bash script (The Fix for macOS)
source "$(conda info --base)/etc/profile.d/conda.sh"

# 2. Check if the Conda environment already exists
if conda info --envs | grep -E -q "\b$ENV_NAME\b"; then
    echo "[Info] Conda environment '$ENV_NAME' already exists."
else
    echo "[Info] Environment '$ENV_NAME' not found. Creating it now..."
    conda env create -n "$ENV_NAME" -f "$REQ_FILE"
    
    if [ $? -ne 0 ]; then
        echo "[Error] Failed to create the conda environment."
        exit 1
    fi
    echo "[Success] Environment created successfully."
fi

# 3. Activate the environment explicitly
echo ""
echo "--> Activating environment: $ENV_NAME"
conda activate "$ENV_NAME"

# 4. Navigate into the SPEOS directory so Python can find the 'speos' module
echo "--> Navigating to external/SPEOS..."
cd external/SPEOS || exit

# 5. Execute the SPEOS Command
echo "--> Executing SPEOS cross-validation..."
echo "Running: python -u $SCRIPT_PATH -c $CONFIG_PATH"
echo "----------------------------------------"

python -u "$SCRIPT_PATH" -c "$CONFIG_PATH"

# Capture the exit code of the Python script
EXIT_CODE=$?

# Navigate back to the root KIML directory
cd ../..

# 6. Handle the exit code
if [ $EXIT_CODE -eq 0 ]; then
    echo "----------------------------------------"
    echo "[Success] SPEOS test completed execution."
else
    echo "----------------------------------------"
    echo "[Error] SPEOS test encountered an error. Check the stack trace above."
    exit 1
fi