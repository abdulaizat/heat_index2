import os
import shutil

# CONFIGURATION
DOWNLOAD_ROOT = "/mnt/AizatDrive"
DIRS = [
    os.path.join(DOWNLOAD_ROOT, "MOD11A1"),
    os.path.join(DOWNLOAD_ROOT, "MOD13A2")
]
QUARANTINE_DIR = os.path.join(DOWNLOAD_ROOT, "_CORRUPT_FILES_QUARANTINE")

def is_valid_header(filepath):
    """Returns True if file has valid HDF4/HDF5/NetCDF magic number."""
    try:
        if os.path.getsize(filepath) < 1000: return False # Too small
        with open(filepath, "rb") as f:
            header = f.read(8)
            if header[:4] == b'\x0e\x03\x13\x01': return True # HDF4
            if header[:8] == b'\x89HDF\r\n\x1a\n': return True # HDF5
            if header[:3] == b'CDF': return True # NetCDF
    except:
        return False
    return False

def analyze_garbage(filepath):
    """Reads the first few lines of a corrupt file to see what it actually is."""
    try:
        with open(filepath, "r", errors='ignore') as f:
            return f.read(100).replace('\n', ' ')
    except:
        return "Unreadable binary"

def main():
    print(f"--- STARTING SANITIZATION PROTOCOL ---")
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    
    total_scanned = 0
    corrupt_count = 0
    
    for directory in DIRS:
        if not os.path.exists(directory): continue
        
        print(f"Scanning: {directory}")
        files = [f for f in os.listdir(directory) if f.endswith(('.hdf', '.h5', '.nc'))]
        
        for filename in files:
            filepath = os.path.join(directory, filename)
            total_scanned += 1
            
            if not is_valid_header(filepath):
                corrupt_count += 1
                
                # Show content of the first failure found
                if corrupt_count == 1:
                    print(f"\n[INSIGHT] Detected corrupt file: {filename}")
                    print(f"[INSIGHT] Internal Content: {analyze_garbage(filepath)}")
                    print(f"[INSIGHT] Conclusion: This is not an image. It's an error log saved as .hdf\n")

                # Move to quarantine
                dest = os.path.join(QUARANTINE_DIR, filename)
                shutil.move(filepath, dest)
                print(f"QUARANTINED: {filename}")

    print("-" * 50)
    print(f"SCAN COMPLETE.")
    print(f"Total Files Scanned: {total_scanned}")
    print(f"Corrupt Files Removed: {corrupt_count}")
    print(f"Moved to: {QUARANTINE_DIR}")
    print("-" * 50)
    
    if corrupt_count > 0:
        print("ACTION REQUIRED: Run your original download script again.")
        print("It will now detect these files are 'missing' and download the real versions.")

if __name__ == "__main__":
    main()