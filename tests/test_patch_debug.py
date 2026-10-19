import os
import sys
from unittest.mock import patch, MagicMock

# Set environment variables for the tests
os.environ["R2_ENDPOINT"] = "https://mock.r2.cloudflarestorage.com"
os.environ["R2_ACCESS_KEY_ID"] = "test_access_key"
os.environ["R2_SECRET_ACCESS_KEY"] = "test_secret_key"
os.environ["R2_BUCKET_NAME"] = "test-bucket"

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

def test_patch_directly():
    # Import the function
    from services.upstox_service import get_expired_historical_candles
    
    # Patch it
    with patch("services.upstox_service.get_expired_historical_candles") as mock_func:
        mock_func.return_value = "test result"
        
        # Call the function
        result = get_expired_historical_candles("token", "instrument", "1minute", "2024-01-15", "2024-01-15")
        
        print(f"Result: {result}")
        print(f"Expected: test result")
        if result == "test result":
            print("SUCCESS: Patch is working")
        else:
            print("FAILURE: Patch is not working")

def test_patch_another_function():
    # Import another function
    from services.upstox_service import get_option_contracts
    
    # Patch it
    with patch("services.upstox_service.get_option_contracts") as mock_func:
        mock_func.return_value = "test result"
        
        # Call the function
        result = get_option_contracts("token", "instrument")
        
        print(f"Result: {result}")
        print(f"Expected: test result")
        if result == "test result":
            print("SUCCESS: Patch on another function is working")
        else:
            print("FAILURE: Patch on another function is not working")

def test_patch_historical_function():
    # Import a function from historical service
    from services.historical_service import get_historical_candles
    
    # Patch a simple function in historical service to see if patching works there
    with patch("services.historical_service.some_nonexistent_function") as mock_func:
        # This should fail if the function doesn't exist, but let's see what happens
        pass
        
    # Actually, let's patch something that does exist
    with patch("services.historical_service.CACHE_DIR") as mock_cache_dir:
        mock_cache_dir.return_value = "/tmp/test"
        from services.historical_service import CACHE_DIR
        print(f"CACHE_DIR: {CACHE_DIR}")
        if str(CACHE_DIR) == "/tmp/test":
            print("SUCCESS: Patch on historical service variable is working")
        else:
            print("FAILURE: Patch on historical service variable is not working")

def test_patch_via_import():
    # Import the function from where it's used in historical service
    from services.historical_service import get_expired_historical_candles as historical_get_expired_historical_candles
    
    # Patch it in the historical service module
    with patch("services.historical_service.get_expired_historical_candles") as mock_func:
        mock_func.return_value = "test result"
        
        # Call the function
        result = historical_get_expired_historical_candles("token", "instrument", "1minute", "2024-01-15", "2024-01-15")
        
        print(f"Result: {result}")
        print(f"Expected: test result")
        if result == "test result":
            print("SUCCESS: Patch via historical service is working")
        else:
            print("FAILURE: Patch via historical service is not working")

if __name__ == "__main__":
    print("Testing direct patch:")
    test_patch_directly()
    print("\nTesting patch via historical service import:")
    test_patch_via_import()