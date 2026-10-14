#!/bin/bash
# run_pipeline.sh

echo "========================================"
echo " Starting KIML Master Pipeline"
echo "========================================"

# 1. Run Mantis in its dedicated Python 3.7 environment
echo ""
echo "--> [Phase 1/2] Executing Mantis Logic (Environment: kiml_mantis)..."
conda run -n kiml_mantis python kiml/run_mantis_module.py

# Check if Mantis failed before running SPEOS
if [ $? -ne 0 ]; then
    echo " Mantis module failed. Aborting pipeline."
    exit 1
fi

# 2. Run SPEOS in its dedicated Python 3.9 environment
echo ""
echo "--> [Phase 2/2] Executing SPEOS Logic (Environment: kiml_speos)..."
conda run -n kiml_speos python kiml/run_speos_module.py

echo ""
echo " Pipeline Complete!"

