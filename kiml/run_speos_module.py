import sys
from pathlib import Path

# 1. Dynamically add the external SPEOS folder to the Python path
BASE_DIR = Path(__file__).resolve().parent.parent
SPEOS_DIR = BASE_DIR / "external" / "SPEOS"
sys.path.append(str(SPEOS_DIR))

# 2. Define strict paths
DATA_DIR = BASE_DIR / "data" / "kiml_data"
INTERMEDIATE_DIR = BASE_DIR / "data" / "intermediate"

def run_speos():
    """Main execution block for the SPEOS phase of KIML."""
    print("\n--- Initializing SPEOS Integration ---")
    
    # Import SPEOS modules here.
    
    # Verify Mantis actually generated the intermediate data
    if not INTERMEDIATE_DIR.exists() or not any(INTERMEDIATE_DIR.iterdir()):
        print(" Error: No intermediate data found from Mantis.")
        sys.exit(1)
        
    print(f"Loading Mantis outputs from: {INTERMEDIATE_DIR}")
    
    # TODO: Load intermediate data and pass it into the SPEOS framework
    
    print("SPEOS Pipeline execution finished successfully.")

if __name__ == "__main__":
    run_speos()