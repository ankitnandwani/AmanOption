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

from services.upstox_service import get_expired_historical_candles, _get_expired_api
import upstox_client
from models.models import Candle
from datetime import datetime
from botocore.exceptions import ClientError

def test_upstox_mock_api():
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
    # Convert to Candle objects for comparison
    expected_candles = [
        Candle(
            timestamp=datetime.fromisoformat(item["interval"]["start_time"].replace("Z", "+00:00")),
            open=item["interval"]["open"],
            high=item["interval"]["high"],
            low=item["interval"]["low"],
            close=item["interval"]["close"],
            volume=item["interval"]["volume"],
            oi=item["interval"]["oi"],
        )
        for item in sample_candle_data["data"]
    ]
    
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
        # Check that we got the expected data structure
        if (isinstance(result, dict) and 
            "data" in result and 
            len(result["data"]) > 0 and
            "interval" in result["data"][0] and
            result["data"][0]["interval"]["start_time"] == "2024-01-15T09:15:00+00:00"):
            print("SUCCESS: Upstox API mock is working correctly")
        else:
            print("FAILURE: Upstox API mock is not working")
            print(f"Expected data structure with candle data")
            print(f"Got: {result}")

if __name__ == "__main__":
    test_upstox_mock_api()