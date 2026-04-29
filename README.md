# Knowledge Inclusive Machine Learning (KIML)

Welcome to the Knowledge Inclusive Machine Learning (KIML) repository. This project implements a comprehensive pipeline for graph-based machine learning, specifically utilizing Knowledge Inclusive Graph Neural Networks (KIGNN) for advanced cross-validation and post-processing evaluation.

## Acknowledgements

This repository builds upon, integrates, and modifies code from the following outstanding external frameworks:
* **SPEOS**
* **Mantis**

*Note for Users:* Because KIML introduces novel datasets and makes internal architectural alterations to the SPEOS and Mantis codebases, we have created a "hard fork" of these repositories. **You do not need to follow the original environment setup guides for SPEOS or Mantis.** This repository provides a unified, self-bootstrapping environment that resolves all dependencies automatically.

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

## Step 2: Running the Pipeline
Once the data is securely downloaded and extracted, you can execute the entire machine learning pipeline using our fully automated, self-bootstrapping script (run_kiml.sh).

Execution Instructions
Make the execution script executable:

Bash
chmod +x run_kiml.sh
Run the pipeline:

Bash
./run_kiml.sh
What the script does automatically:
Environment Setup: On the very first run, it reads the strictly versioned requirements.yaml file and natively builds the speos_kiml Conda environment. This may take 10-15 minutes initially but will be instantly cached for all future runs.

Cross-Validation: It navigates into the internal SPEOS directory and triggers outer_crossval.py using the specified YAML configuration.

Evaluation: Upon successful training, it safely chains the post-processing scripts, sequentially running summarize_output_probabilities.py and evaluate_results.py to generate your final metrics.

Modifying the Experiment
By default, the script runs the Exp_DEE_KIGNN experiment on the dee dataset. If you wish to run a different experiment or test a different dataset, open run_kiml.sh in your preferred text editor and simply modify the variables at the top of the file:

Bash
## --- Experiment Variables ---
EXP_NAME="Exp_DEE_KIGNN"
DATASET="dee"
The script will automatically update all configuration paths and downstream evaluation arguments dynamically based on these two variables.