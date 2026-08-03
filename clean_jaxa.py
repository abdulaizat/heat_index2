import os

BASE_DIR = "./malaysia_amsr2_jaxa_fedeo"
MIN_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB threshold

def clean_corrupt_files():
    print(f"--- STARTING DEEP CLEAN ---")
    print(f"Target: {BASE_DIR}")
    print(f"Criteria: Delete files smaller than {MIN_SIZE_BYTES/1024/1024} MB")
    
    deleted_count = 0
    reclaimed_space = 0
    
    for root, dirs, files in os.walk(BASE_DIR):
        for name in files:
            file_path = os.path.join(root, name)
            
            try:
                size = os.path.getsize(file_path)
                
                # Check 1: Is it too small? (Corrupt download / HTML error page)
                if size < MIN_SIZE_BYTES:
                    print(f"[DELETE] {name} ({size} bytes)")
                    os.remove(file_path)
                    deleted_count += 1
                    reclaimed_space += size
                    
            except Exception as e:
                print(f"[ERROR] Could not process {name}: {e}")

    print("\n" + "="*40)
    print("CLEANUP SUMMARY")
    print("="*40)
    print(f"Files Deleted:   {deleted_count}")
    print(f"Space Reclaimed: {reclaimed_space / 1024:.2f} KB")
    print("="*40)
    print("You are now ready to run the final download script.")

if __name__ == "__main__":
    clean_corrupt_files()