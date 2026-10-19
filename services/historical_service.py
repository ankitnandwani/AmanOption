from datetime import datetime
import pickle
from pathlib import Path
import os

import requests

from models.config import BASE_URL_V3
from models.models import Candle
from services.upstox_service import get_expired_historical_candles
from services.r2_service import get_object, object_exists, put_object

CACHE_DIR = Path("historical_cache")
CACHE_DIR.mkdir(exist_ok=True)

# R2 bucket name from environment variable
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "amanoptions-historical-cache")

def get_historical_candles(
    access_token: str,
    instrument_key: str,
    from_date: str,
    to_date: str,
    interval: int = 1,
):
    # Use the SDK for expired historical data (backtest mode)
    interval_str = f"{interval}minute"

    # Cache per day (or per date range). Store all contracts for a given day in a single cache file.
    # The cache file name is based on the from_date and to_date (they are typically the same day in backtests).
    day_key = f"{from_date}_{to_date}" if from_date != to_date else from_date
    cache_file = CACHE_DIR / f"{day_key}.pkl"
    r2_key = f"historical_cache/{day_key}.pkl"

    # First, try to load from local cache
    day_cache = {}
    local_cache_hit = False
    if cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                day_cache = pickle.load(f) or {}
            local_cache_hit = True
        except Exception as e:
            print(f"Error reading cache file {cache_file}: {e}")
            day_cache = {}

    # Return cached data if we already have candles for this instrument on this day (local cache hit)
    if local_cache_hit and instrument_key in day_cache:
        return day_cache[instrument_key]

    # If not in local cache, check R2
    if not local_cache_hit or instrument_key not in day_cache:
        # Try to get the cache file from R2
        r2_data = get_object(R2_BUCKET_NAME, r2_key)
        if r2_data is not None:
            try:
                r2_cache = pickle.loads(r2_data) or {}
                # If we have data for this instrument in R2, use it
                if instrument_key in r2_cache:
                    # Optionally store in local cache for future requests (but don't overwrite if we had a partial local cache)
                    if not local_cache_hit:
                        day_cache = r2_cache
                    elif instrument_key not in day_cache:
                        day_cache[instrument_key] = r2_cache[instrument_key]
                    # Save to local cache
                    try:
                        with open(cache_file, "wb") as f:
                            pickle.dump(day_cache, f)
                    except Exception as e:
                        print(f"Error saving day cache file {cache_file}: {e}")
                    return r2_cache[instrument_key]
                # If not in R2 cache, we'll fall through to Upstox
                else:
                    # Still store the R2 data locally for potential future use
                    if not local_cache_hit:
                        day_cache = r2_cache
                    elif not day_cache:  # Only if we don't have any local data yet
                        day_cache = r2_cache
                    # Save the R2 data locally
                    try:
                        with open(cache_file, "wb") as f:
                            pickle.dump(day_cache, f)
                    except Exception as e:
                        print(f"Error saving day cache file {cache_file}: {e}")
            except Exception as e:
                print(f"Error processing R2 data for {r2_key}: {e}")
                # Continue to Upstox fetch

    # If we get here, we need to fetch from Upstox (local miss and R2 miss or error)
    print(f"CACHE MISS: Fetching {instrument_key} from API for {day_key}...")
    response = get_expired_historical_candles(
        access_token,
        instrument_key,
        interval_str,
        from_date,
        to_date,
    )

    if response is None:
        print(f"API Error: Response is None for {instrument_key}")
        return []

    candles = []
    # Extract candle list from the SDK response. The Upstox SDK may return a HistoricalCandleData object with a
    # ``data`` attribute that is either a dict containing ``candles`` or an object with its own ``candles`` attribute.
    # It may also directly return a dict (e.g., from a mocked response). Handle all reasonable shapes to obtain a list of candle rows.
    if isinstance(response, dict):
        # Direct dict response; attempt to locate candles
        if "candles" in response:
            data = response["candles"]
        elif "data" in response:
            inner = response["data"]
            if isinstance(inner, dict) and "candles" in inner:
                data = inner["candles"]
            else:
                data = inner
        else:
            data = response
    elif hasattr(response, "candles"):
        # Direct attribute, already a list
        data = response.candles
    elif hasattr(response, "data"):
        # ``data`` may be a dict or an object
        inner = response.data
        if isinstance(inner, dict) and "candles" in inner:
            data = inner["candles"]
        elif hasattr(inner, "candles"):
            data = inner.candles
        else:
            # Fallback: use the inner object as‑is; may be a list
            data = inner
    else:
        # Unexpected shape; treat the response itself as the data container
        data = response

    if not data or not isinstance(data, (list, tuple)):
        print(f"API Error: No valid candle data for {instrument_key}. Data type: {type(data)}")
        # No valid data; keep candles empty and proceed to caching
    else:
        for row in data:
            if isinstance(row, (list, tuple)):
                candles.append(
                    Candle(
                        timestamp=datetime.fromisoformat(
                            row[0].replace("Z", "+00:00")
                        ),
                        open=row[1],
                        high=row[2],
                        low=row[3],
                        close=row[4],
                        volume=row[5],
                        oi=row[6],
                    )
                )
            else:
                candles.append(
                    Candle(
                        timestamp=datetime.fromisoformat(
                            row.timestamp.replace("Z", "+00:00")
                        ),
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        volume=row.volume,
                        oi=row.oi,
                    )
                )

    result = list(reversed(candles))

    # Update the per‑day cache dict and persist it to both local cache and R2
    day_cache[instrument_key] = result
    try:
        # Save to local cache
        with open(cache_file, "wb") as f:
            pickle.dump(day_cache, f)
        # Save to R2
        pickle_data = pickle.dumps(day_cache)
        put_object(R2_BUCKET_NAME, r2_key, pickle_data)
    except Exception as e:
        print(f"Error saving day cache file {cache_file}: {e}")

    if not result:
        print(f"No candles found for {instrument_key}. Cached empty result.")

    return result
