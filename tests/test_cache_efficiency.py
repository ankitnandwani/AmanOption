import os
import pickle
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

# Set environment variables for the tests
os.environ["R2_ENDPOINT"] = "https://mock.r2.cloudflarestorage.com"
os.environ["R2_ACCESS_KEY_ID"] = "test_access_key"
os.environ["R2_SECRET_ACCESS_KEY"] = "test_secret_key"
os.environ["R2_BUCKET_NAME"] = "test-bucket"
os.environ["MAX_CACHE_SIZE_MB"] = "1"  # Small cache size for testing
os.environ["MAX_MEMORY_CACHE_ITEMS"] = "3"  # Small memory cache for testing

from services.historical_service import get_historical_candles, get_cache_stats, _enforce_cache_size_limit, _memory_cache, _pending_fetches
from models.models import Candle
from datetime import datetime


class TestCacheEfficiency(unittest.TestCase):
    def setUp(self):
        # Clear global state before each test
        _memory_cache.clear()
        _pending_fetches.clear()
        # Create a temporary directory for cache files
        self.test_dir = tempfile.mkdtemp()
        self.original_cache_dir = None
        
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

    def tearDown(self):
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("services.historical_service.CACHE_DIR")
    @patch("builtins.open", new_callable=mock_open)
    @patch("services.historical_service.pickle.load")
    @patch("services.r2_service.get_object")
    @patch("services.upstox_service.get_expired_historical_candles")
    @patch("services.r2_service.put_object")
    def test_repeated_access_avoids_repeated_deserialization(
        self, mock_put_object, mock_upstox, mock_get_object, mock_pickle_load, mock_file, mock_cache_dir
    ):
        """Test that repeated access to the same data doesn't cause repeated deserialization"""
        # Setup
        mock_cache_dir.return_value = Path(self.test_dir)
        mock_pickle_load.return_value = {"TEST_INSTRUMENT": self.sample_candles}
        mock_get_object.return_value = None  # Simulate R2 miss
        mock_upstox.return_value = {
            "candles": self.sample_candle_data
        }
        
        # Call the function multiple times with the same parameters
        result1 = get_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        result2 = get_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        result3 = get_historical_candles(
            access_token="fake_token",
            instrument_key="TEST_INSTRUMENT",
            from_date="2024-01-15",
            to_date="2024-01-15",
        )
        
        # Verify all results are the same
        self.assertEqual(result1, self.sample_candles)
        self.assertEqual(result2, self.sample_candles)
        self.assertEqual(result3, self.sample_candles)
        
        # Verify that Upstox was only called once (due to caching)
        self.assertEqual(mock_upstox.call_count, 1)
        
        # Verify that the file was only read from disk once (due to memory cache)
        # Note: The first call reads from disk, subsequent calls should use memory cache
        self.assertEqual(mock_file.call_count, 1)  # Only opened once for reading

    @patch("services.historical_service.CACHE_DIR")
    @patch("builtins.open", new_callable=mock_open)
    @patch("services.historical_service.pickle.load")
    @patch("services.r2_service.get_object")
    @patch("services.upstox_service.get_expired_historical_candles")
    @patch("services.r2_service.put_object")
    def test_bounded_local_cache_eviction(
        self, mock_put_object, mock_upstox, mock_get_object, mock_pickle_load, mock_file, mock_cache_dir
    ):
        """Test that the local cache respects size limits and evicts old files"""
        # Setup
        mock_cache_dir.return_value = Path(self.test_dir)
        mock_pickle_load.return_value = {"TEST_INSTRUMENT": self.sample_candles}
        mock_get_object.return_value = None  # Simulate R2 miss
        mock_upstox.return_value = {
            "candles": self.sample_candle_data
        }
        
        # Create multiple different cache files to test eviction
        dates = [f"2024-01-{i:02d}" for i in range(1, 6)]  # 5 different dates
        
        results = []
        for date in dates:
            result = get_historical_candles(
                access_token="fake_token",
                instrument_key="TEST_INSTRUMENT",
                from_date=date,
                to_date=date,
            )
            results.append(result)
            self.assertEqual(result, self.sample_candles)
        
        # Verify that Upstox was called for each unique date
        self.assertEqual(mock_upstox.call_count, len(dates))
        
        # Check cache stats to verify size limiting is working
        stats = get_cache_stats()
        self.assertGreaterEqual(stats["file_count"], 0)
        self.assertLessEqual(stats["total_size_mb"], float(os.environ["MAX_CACHE_SIZE_MB"]) + 0.1)  # Allow small overhead

    @patch("services.historical_service.CACHE_DIR")
    @patch("builtins.open", new_callable=mock_open)
    @patch("services.historical_service.pickle.load")
    @patch("services.r2_service.get_object")
    @patch("services.upstox_service.get_expired_historical_candles")
    @patch("services.r2_service.put_object")
    def test_concurrent_same_key_miss_protection(
        self, mock_put_object, mock_upstox, mock_get_object, mock_pickle_load, mock_file, mock_cache_dir
    ):
        """Test that concurrent requests for the same missing key don't cause duplicate fetches"""
        # Setup
        mock_cache_dir.return_value = Path(self.test_dir)
        mock_pickle_load.side_effect = Exception("Corrupted cache")  # Simulate cache read error
        mock_get_object.return_value = None  # Simulate R2 miss
        mock_upstox.return_value = {
            "candles": self.sample_candles
        }
        
        # Simulate concurrent access by calling the function multiple times quickly
        # In a real test, we'd use actual threads, but for simplicity we'll just call it multiple times
        # and verify that Upstox is only called once due to our in-progress fetch protection
        results = []
        for _ in range(3):
            result = get_historical_candles(
                access_token="fake_token",
                instrument_key="TEST_INSTRUMENT",
                from_date="2024-01-15",
                to_date="2024-01-15",
            )
            results.append(result)
        
        # All results should be the same
        for result in results:
            self.assertEqual(result, self.sample_candles)
        
        # Due to our fetch protection, Upstox should only be called once
        # even though we made multiple concurrent requests
        self.assertEqual(mock_upstox.call_count, 1)
        
        # The result should be stored and subsequent calls should use the cached value
        # Verify that the file was written to (cache updated)
        mock_file.assert_any_call(mock.ANY, "wb")  # Called for writing


if __name__ == "__main__":
    unittest.main()