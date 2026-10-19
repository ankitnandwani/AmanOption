import os
import pickle
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from botocore.exceptions import ClientError

# Set environment variables for the tests
os.environ["R2_ENDPOINT"] = "https://mock.r2.cloudflarestorage.com"
os.environ["R2_ACCESS_KEY_ID"] = "test_access_key"
os.environ["R2_SECRET_ACCESS_KEY"] = "test_secret_key"
os.environ["R2_BUCKET_NAME"] = "test-bucket"

from services.historical_service import get_historical_candles
from services.r2_service import _s3_client as r2_s3_client
from models.models import Candle
from datetime import datetime


class TestHistoricalService(unittest.TestCase):
    def setUp(self):
        # Reset R2 service singleton client before each test
        global r2_s3_client
        r2_s3_client = None
        print(f"[SETUP] Reset r2_s3_client to {r2_s3_client}")
    def setUp(self):
        # Sample candle data for testing
        self.sample_candle_data = [
            (
                "2024-01-15T09:15:00+00:00",
                100.0,
                105.0,
                99.0,
                102.0,
                1000,
                50000,
            )
        ]
        self.sample_candles = [
            Candle(
                timestamp=datetime.fromisoformat(row[0].replace("Z", "+00:00")),
                open=row[1],
                high=row[2],
                low=row[3],
                close=row[4],
                volume=row[5],
                oi=row[6],
            )
            for row in self.sample_candle_data
        ]

    @patch("services.historical_service.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("services.historical_service.pickle.load")
    def test_local_cache_hit(self, mock_pickle_load, mock_file, mock_path_exists):
        """Test that data is returned from local cache when available"""
        # Setup mocks
        mock_path_exists.return_value = True
        mock_pickle_load.return_value = {"TEST_INSTRUMENT": self.sample_candles}
        
        # Call function
        result = get_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        # Verify
        self.assertEqual(result, self.sample_candles)
        mock_path_exists.assert_called_once()
        mock_file.assert_called_once()
        mock_pickle_load.assert_called_once()

    @patch("services.historical_service.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("services.historical_service.pickle.load")
    @patch("services.r2_service.get_client")
    def test_r2_cache_hit(self, mock_get_client, mock_pickle_load, mock_file, mock_path_exists):
        """Test that data is returned from R2 when not in local cache but available in R2"""
        # Setup mocks - local cache miss
        mock_path_exists.return_value = False  # No local cache file
        
        # Setup R2 service mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        test_data = pickle.dumps({"TEST_INSTRUMENT": self.sample_candles})
        # Configure mock client methods
        mock_response = {"Body": MagicMock(read=MagicMock(return_value=test_data))}
        mock_client.get_object.return_value = mock_response
        mock_client.put_object.return_value = {}  # put_object doesn't need to return anything specific
        mock_pickle_load.return_value = {"TEST_INSTRUMENT": self.sample_candles}
        
        # Call function
        result = get_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        # Verify
        self.assertEqual(result, self.sample_candles)
        mock_path_exists.assert_called_once()
        mock_get_client.assert_called_once()
        mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="historical_cache/2024-01-15.pkl")
        # Note: We save to local cache (via open) but NOT to R2 since we just got it from R2
        mock_client.put_object.assert_not_called()

    @patch("services.historical_service.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("services.historical_service.pickle.load")
    @patch("services.r2_service.get_client")
    @patch("services.upstox_service._get_expired_api")
    def test_full_miss_local_and_r2_then_upstox(
        self, mock_get_api, mock_get_client, mock_pickle_load, mock_file, mock_path_exists
    ):
        """Test that data is fetched from Upstox when not in local cache or R2, then stored to both"""
        # Setup mocks - local cache miss, R2 miss, then Upstox hit
        mock_path_exists.return_value = False  # No local cache file
        
        # Setup R2 service mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # Simulate R2 object not found by raising ClientError with 404
        from botocore.exceptions import ClientError
        error_response = {'Error': {'Code': '404'}}
        mock_client.get_object.side_effect = ClientError(error_response, 'GetObject')
        mock_client.put_object.return_value = {}  # put_object doesn't need to return anything specific
        
        # Setup Upstox service mock
        mock_api = MagicMock()
        mock_get_api.return_value = mock_api
        # Format data as list of lists/tuples as expected by historical service
        # Format: [timestamp_string, open, high, low, close, volume, oi]
        sample_candle_data = [
            [
                "2024-01-15T09:15:00+00:00",  # timestamp
                100.0,                         # open
                105.0,                         # high
                99.0,                          # low
                102.0,                         # close
                1000,                          # volume
                50000                          # oi
            ]
        ]
        mock_api.get_expired_historical_candle_data.return_value = {"data": sample_candle_data}
        
        # Setup pickle mocks for local cache operations
        mock_pickle_load.return_value = {}  # Empty cache when loading
        
        # Call function
        result = get_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        # Verify
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open, 100.0)
        self.assertEqual(result[0].high, 105.0)
        self.assertEqual(result[0].low, 99.0)
        self.assertEqual(result[0].close, 102.0)
        self.assertEqual(result[0].volume, 1000)
        self.assertEqual(result[0].oi, 50000)
        mock_path_exists.assert_called_once()
        self.assertEqual(mock_get_client.call_count, 2)
        mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="historical_cache/2024-01-15.pkl")
        mock_get_api.assert_called_once()
        mock_api.get_expired_historical_candle_data.assert_called_once_with(
            "TEST_INSTRUMENT", "1minute", "2024-01-15", "2024-01-15"
        )
        # Should save to both local cache (via open) and R2 (via put_object)
        # Note: local cache saving happens through the open() mock, so we check for file write calls
        # R2 saving happens through put_object
        self.assertEqual(mock_client.put_object.call_count, 1)
        # Check that put_object was called with the right pickle data
        mock_client.put_object.assert_called_with(
            Bucket="test-bucket",
            Key="historical_cache/2024-01-15.pkl",
            Body=unittest.mock.ANY  # We'll check the data separately if needed
        )

    @patch("services.historical_service.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("services.historical_service.pickle.load")
    @patch("services.r2_service.get_client")
    @patch("services.upstox_service._get_expired_api")
    def test_persistence_after_upstox_fetch(
        self, mock_get_api, mock_get_client, mock_pickle_load, mock_file, mock_path_exists
    ):
        """Test that after fetching from Upstox, data is persisted to both local cache and R2"""
        # Setup mocks
        mock_path_exists.return_value = False  # No local cache initially
        
        # Setup R2 service mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        # Simulate R2 object not found by raising ClientError with 404
        from botocore.exceptions import ClientError
        error_response = {'Error': {'Code': '404'}}
        mock_client.get_object.side_effect = ClientError(error_response, 'GetObject')
        mock_client.put_object.return_value = {}  # put_object doesn't need to return anything specific
        
        # Setup Upstox service mock
        mock_api = MagicMock()
        mock_get_api.return_value = mock_api
        # Format data as list of lists/tuples as expected by historical service
        # Format: [timestamp_string, open, high, low, close, volume, oi]
        sample_candle_data = [
            [
                "2024-01-15T09:15:00+00:00",  # timestamp
                100.0,                         # open
                105.0,                         # high
                99.0,                          # low
                102.0,                         # close
                1000,                          # volume
                50000                          # oi
            ]
        ]
        mock_api.get_expired_historical_candle_data.return_value = {"data": sample_candle_data}
        
        # Setup pickle mocks for local cache operations
        mock_pickle_load.return_value = {}  # Empty cache when loading
        
        # Call function
        result = get_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        # Verify data was returned
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open, 100.0)
        self.assertEqual(result[0].high, 105.0)
        self.assertEqual(result[0].low, 99.0)
        self.assertEqual(result[0].close, 102.0)
        self.assertEqual(result[0].volume, 1000)
        self.assertEqual(result[0].oi, 50000)
        
        # Verify persistence calls
        # Should have called put_object for R2 persistence
        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket", 
            Key="historical_cache/2024-01-15.pkl", 
            Body=unittest.mock.ANY  # The pickle data
        )
        
        # Verify that file was opened for writing (local cache persistence)
        mock_file.assert_any_call(unittest.mock.ANY, "wb")


if __name__ == "__main__":
    unittest.main()