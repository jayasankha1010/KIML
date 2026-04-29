import os
import zipfile
from pathlib import Path
import subprocess
import sys

# --- CONFIGURATION ---
# Your specific Google Drive File ID
GDRIVE_FILE_ID = "1fjnxffteL7B-vphWviYhZYENyt-HvFhk"

# Define paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ARCHIVE_PATH = DATA_DIR / "kiml_data.zip"

def ensure_gdown_installed():
    """Ensures gdown is installed, as it's required to bypass GDrive virus warnings."""
    try:
        import gdown
    except ImportError:
        print(" 'gdown' library not found. Installing it now...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown"])
        print(" 'gdown' installed successfully.\n")

def setup_gdrive_data():
    """Downloads the zip from Google Drive and extracts it."""
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if data is already extracted
    if (DATA_DIR / "DEE").exists() or (DATA_DIR / "pubmed_embeddings").exists():
        print("Data appears to be already extracted. Ready to run.")
        return

    print(" Downloading KIML dataset from Google Drive...")
    
    # We must import gdown here, AFTER the ensure_gdown_installed() check
    import gdown 
    
    try:
        # gdown requires the format: https://drive.google.com/uc?id=FILE_ID
        download_url = f"https://drive.google.com/uc?id={GDRIVE_FILE_ID}"
        
        # gdown automatically handles the >100MB warning and streams the file
        gdown.download(download_url, str(ARCHIVE_PATH), quiet=False)
        
        if not ARCHIVE_PATH.exists():
            raise Exception("File failed to download. Check if the GDrive link is set to 'Anyone with the link'.")
            
    except Exception as e:
        print(f" Error during download: {e}")
        return 

    print("\n📦 Extracting directories and files...")
    try:
        with zipfile.ZipFile(ARCHIVE_PATH, 'r') as zip_ref:
            zip_ref.extractall(DATA_DIR)
        print(" Extraction complete! Data is ready to use.")
        
        # Clean up the zip file
        os.remove(ARCHIVE_PATH)
        print("🧹 Cleaned up zip archive.")
        
    except zipfile.BadZipFile:
        print(" Error: The downloaded file is not a valid zip archive.")
        print("Ensure your Google Drive file is publicly shared and is a true .zip file.")

if __name__ == "__main__":
    print("Initializing KIML Data Setup (Google Drive Staging)...\n")
    ensure_gdown_installed()
    setup_gdrive_data()