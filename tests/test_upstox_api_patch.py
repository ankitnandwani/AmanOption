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

def test_upstox_api_patch():
    from services.upstox_service import get_expired_historical_candles, _get_expired_api
    import upstox_client
    
    sample_candle_data = {
        "data": [
            {
                "interval": {
                    "start_time": "2024-01-15T09:15:00+00:00",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 102.0,
                    "volume": 1000,
                    "oi": 50000
                }
            }
        ]
    }
    
    # Patch the _get_expired_api function
    with patch("services.upstox_service._get_expired_api") as mock_get_api:
        # Create a mock API instance
        mock_api = MagicMock()
        mock_get_api.return_value = mock_api
        
        # Configure the mock API instance's method
        mock_api.get_expired_historical_candle_data.return_value = sample_candle_data
        
        # Call the function
        result = get_expired_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            interval="1minute",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        print(f"Result: {result}")
        if result == sample_candle_data:
            print("SUCCESS: Upstox API patch is working")
        else:
            print("FAILURE: Upstox API patch is not working")
            print(f"Expected: {sample_candle_data}")
            print(f"Got: {result}")

if __name__ == "__main__":
    test_upstox_api_patch()