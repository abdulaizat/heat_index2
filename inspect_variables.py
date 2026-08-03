import earthaccess
import xarray as xr

def inspect_granule_structure():
    auth = earthaccess.login(strategy="interactive", persist=True)
    
    results = earthaccess.search_data(
        short_name="SPL4SMGP",
        version="008",
        count=1
    )
    
    if not results:
        print("No granules found.")
        return

    # Open the first result
    files = earthaccess.open(results)
    
    if not files:
        print("Could not open files.")
        return
        
    print(f"Opening {files[0]}...")
    
    # Try opening with xarray
    try:
        ds = xr.open_dataset(files[0], engine='h5netcdf') 
        # Note: SPL4SMGP is HDF5. h5netcdf engine is good.
        # Sometimes it might need group paths.
        print("\n--- Dataset Variables ---")
        print(list(ds.data_vars))
        print("\n--- Dataset Coordinates ---")
        print(list(ds.coords))
        
        # If variables are nested in groups, xarray might not show them at root.
        # We might need to inspect groups if data_vars is empty or sparse.
        print("\n--- Full Info ---")
        print(ds)
        
    except Exception as e:
        print(f"Error opening with xarray: {e}")
        # Fallback: try to list keys if it acts like a file object
        try:
            import h5py
            with h5py.File(files[0], 'r') as f:
                print("\n--- HDF5 Keys ---")
                def print_attrs(name, obj):
                    print(name)
                f.visititems(print_attrs)
        except ImportError:
            print("h5py not installed.")
        except Exception as e2:
            print(f"Error with h5py: {e2}")

if __name__ == "__main__":
    inspect_granule_structure()
