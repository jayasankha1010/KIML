import sys
from pathlib import Path

# 1. Dynamically add the external Mantis folder to the Python path
BASE_DIR = Path(__file__).resolve().parent.parent
MANTIS_DIR = BASE_DIR / "external" / "Mantis"
sys.path.append(str(MANTIS_DIR))

# 2. Define strict paths based on your current directory tree
DATA_DIR = BASE_DIR / "data" / "kiml_data"
MANTIS_INPUTS = DATA_DIR / "mantis_Input_Files"
PUBMED_EMBEDDINGS = DATA_DIR / "pubmed_embeddings"

# This is where Mantis will drop its processed files for SPEOS to pick up
INTERMEDIATE_DIR = BASE_DIR / "data" / "intermediate"

def run_mantis():
    """Main execution block for the Mantis phase of KIML."""
    print("\n--- Initializing Mantis Integration ---")
    
    # Ensure the intermediate directory exists
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Import Mantis modules here. 
    # Example: from mantis_ml.modules.main import ...
    
    print(f"Reading base inputs from: {MANTIS_INPUTS}")
    print(f"Injecting general context from: {PUBMED_EMBEDDINGS}")
    
    # TODO: Write the logic to feed PubMed embeddings into the Mantis graph
    
    print(f"Saving intermediate tensors/graphs to: {INTERMEDIATE_DIR}")
    # TODO: Save the output files that SPEOS will need
    
if __name__ == "__main__":
    run_mantis()