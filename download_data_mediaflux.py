import os
import urllib.request
import zipfile
from pathlib import Path

# The direct content stream link you provided
DOWNLOAD_URL = "https://mediaflux.researchsoftware.unimelb.edu.au/mflux/content.mfjp?_skey=7fnOzUulBejaRIWjsO7fZPyZSoBD6tLP/13e/1829a27&id=2771737428&version=1"

# Define paths relative to this script
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ARCHIVE_PATH = DATA_DIR / "kiml_data.zip"

def setup_data():
    """Downloads the zip archive directly from Mediaflux and extracts it."""
    
    # Ensure the target data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Simple check to prevent re-downloading if data is already present.
    # (Optional: Change "DEE" to the name of one of the specific sub-folders inside your zip)
    if (DATA_DIR / "DEE").exists() or (DATA_DIR / "pubmed_embeddings").exists():
        print("✅ Data appears to be already extracted. Ready to run.")
        return

    print("⬇️ Downloading KIML dataset archive from Mediaflux...")
    try:
        # Add a generic User-Agent to prevent server blocking
        req = urllib.request.Request(DOWNLOAD_URL, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req) as response, open(ARCHIVE_PATH, 'wb') as out_file:
            # Stream the file in 8KB chunks
            chunk_size = 8192
            downloaded = 0
            
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                
                # Print progress every ~50MB to show it hasn't frozen
                if downloaded % (1024 * 1024 * 50) < chunk_size and downloaded > 0:
                    print(f"   ... {downloaded / (1024 * 1024):.0f} MB downloaded")
                    
        print(f"✅ Download complete! Saved temporary archive to data/kiml_data.zip")
        
    except Exception as e:
        print(f"❌ Error during download: {e}")
        return # Stop execution if download fails

    print("📦 Extracting directories and files...")
    try:
        with zipfile.ZipFile(ARCHIVE_PATH, 'r') as zip_ref:
            # Extract everything directly into the data folder
            zip_ref.extractall(DATA_DIR)
        print("✅ Extraction complete! Data is ready to use.")
        
        # Clean up the zip file to save server space
        os.remove(ARCHIVE_PATH)
        print("🧹 Cleaned up zip archive.")
        
    except zipfile.BadZipFile:
        print("❌ Error: The downloaded file is not a valid zip archive.")
        print("The link might be expired, or the server returned an error page instead of the file.")

if __name__ == "__main__":
    print("Initializing KIML Data Setup...\n")
    setup_data()