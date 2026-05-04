# Knowledge Inclusive Machine Learning (KIML)

Welcome to the Knowledge Inclusive Machine Learning (KIML) repository. This project implements a comprehensive pipeline for machine learning in genomics and healthcare, featuring two distinct architectural approaches:
1. **KIGNN:** Knowledge Inclusive Graph Neural Networks (built on SPEOS).
2. **KIRF:** Knowledge Inclusive Random Forests / XGBoost (built on Mantis).

## Acknowledgements

This repository builds upon, integrates, and modifies code from the following outstanding external frameworks:
* **SPEOS** (for the KIGNN pipeline)
* **Mantis** (for the KIRF pipeline)

*Note for Users:* Because KIML introduces novel datasets and makes internal architectural alterations to the SPEOS and Mantis codebases, we have created a "hard fork" of these repositories. **You do not need to follow the original environment setup guides for SPEOS or Mantis.** This repository provides unified, self-bootstrapping execution scripts that resolve all legacy dependencies (including Nextflow and older TensorFlow versions) automatically.

## Prerequisites

Before interacting with this repository, ensure your system meets the following requirements:
* **Operating System:** A Linux-based environment (e.g., Ubuntu server, AWS EC2 instance, or an HPC cluster).
* **Hardware:** An NVIDIA GPU.
* **Drivers:** NVIDIA drivers compatible with CUDA 12.1+ (for PyTorch integration).
* **Software Manager:** Anaconda or Miniconda installed and initialized in your terminal.
* **Python:** A base Python installation to execute the initial data setup script.

---

## Step 1: Data Download & Preparation

The KIML pipeline requires specific datasets (e.g., `mantis_Input_Files` and `pubmed_embeddings`) to function. We have provided an automated script that securely downloads the necessary data archive from Google Drive, extracts it into the correct directories, and cleans up temporary files.

1. Ensure you are in the root directory of the cloned `KIML` repository.
2. Run the data setup script:
   ```bash
   python setup_data.py
   ```
*(Note: This script will automatically install the lightweight `gdown` library to your current active environment to safely bypass Google Drive's large-file virus scan warnings, and it will clean up any hidden macOS metadata folders during extraction).*

---

## Step 2: Running the Pipelines

We provide fully automated, self-bootstrapping scripts for both architectures. On their first run, these scripts will natively build their respective Conda environments (`speos_kiml` or `mantis_kiml`), patch legacy dependencies, execute the models, and run post-processing evaluation.

### Option A: Graph Neural Network (KIGNN)
The KIGNN pipeline uses PyTorch Geometric for spatial graph-based learning.

**To run locally (Standard Linux Server):**
```bash
chmod +x run_kignn.sh
./run_kignn.sh
```

**To run on an HPC Cluster (SLURM):**
```bash
sbatch run_kignn_on_gpu_cluster.slurm
```
*Outputs for this pipeline are automatically routed to the `GNN_results/` directory.*

### Option B: Random Forest (KIRF)
The KIRF pipeline uses Nextflow to orchestrate XGBoost/Random Forest models for semi-supervised learning.

**To run locally (Standard Linux Server):**
```bash
chmod +x run_kirf.sh
./run_kirf.sh
```

**To run on an HPC Cluster (SLURM):**
```bash
sbatch run_kirf_on_gpu_cluster.slurm
```
*Outputs for this pipeline are automatically routed to the `RF_results/` directory.*

---

## Modifying the Experiment

By default, the scripts are configured to run the `dee` dataset experiment. If you wish to run a different experiment or test a different dataset, open the respective execution script (`.sh` or `.slurm`) in your preferred text editor and modify the experiment variables near the top of the file:

```bash
# --- Experiment Variables ---
EXP_NAME="Exp_DEE_KIGNN" # (or Exp_DEE_KIRF)
DATASET="dee"
```
The script will automatically update all internal configuration paths and downstream evaluation arguments dynamically based on these variables.