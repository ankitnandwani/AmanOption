from datetime import datetime
import pickle
from pathlib import Path
import os
import threading
import time
from collections import OrderedDict

import requests

from models.config import BASE_URL_V3
from models.models import Candle
from services.upstox_service import get_expired_historical_candles
from services.r2_service import get_object, object_exists, put_object
from services.cache_keys import R2_KEY_PREFIX, cache_file_name

CACHE_DIR = Path("historical_cache")
CACHE_DIR.mkdir(exist_ok=True)

# R2 bucket name from environment variable
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "amanoptions-historical-cache")

# Bounded local cache settings.
#
# MAX_CACHE_SIZE_MB controls how much disk the local cache may occupy:
#   * greater than 0 : once the cache is larger than this many megabytes, the
#                       least recently written cache files are deleted to bring
#                       it back under the limit.
#   * 0 or negative   : unlimited. No cache file is ever deleted.
#
# When the variable is not set, the default is 500 MB on Render (its filesystem
# is ephemeral and must stay bounded) and unlimited everywhere else, so a local
# development machine never silently deletes market data that was just
# downloaded. Set MAX_CACHE_SIZE_MB explicitly to override either way.
DEFAULT_RENDER_CACHE_SIZE_MB = 500


def _resolve_max_cache_size_mb() -> int:
    """Resolve the local cache size limit in megabytes (0 means unlimited)."""
    raw = os.getenv("MAX_CACHE_SIZE_MB")
    if raw is not None and raw.strip() != "":
        try:
            return int(raw)
        except ValueError:
            print(f"Warning: ignoring invalid MAX_CACHE_SIZE_MB={raw!r}")
    # Render sets RENDER=true for every service (build time and runtime).
    if os.getenv("RENDER", "").strip().lower() == "true":
        return DEFAULT_RENDER_CACHE_SIZE_MB
    return 0


MAX_CACHE_SIZE_MB = _resolve_max_cache_size_mb()
MAX_CACHE_SIZE_BYTES = MAX_CACHE_SIZE_MB * 1024 * 1024
CACHE_EVICTION_ENABLED = MAX_CACHE_SIZE_BYTES > 0

# Eviction runs after every contract write. A full directory scan per write is
# expensive, so scans are throttled and the running size estimate lets the
# common case skip the scan entirely.
_ENFORCE_INTERVAL_SECONDS = 5.0
_last_enforcement_time = 0.0
_cache_size_estimate = 0

if CACHE_EVICTION_ENABLED:
    print(
        f"Local cache limit: {MAX_CACHE_SIZE_MB} MB "
        f"(cache files are deleted when the limit is exceeded)"
    )
else:
    print("Local cache: unlimited size (no cache file will be deleted)")

# In-memory cache for recently accessed items to avoid repeated deserialization
# Using OrderedDict for LRU-like behavior
_memory_cache = OrderedDict()
_memory_cache_lock = threading.Lock()
_MAX_MEMORY_CACHE_ITEMS = int(os.getenv("MAX_MEMORY_CACHE_ITEMS", "10"))  # Default 10 items

# Simple locking mechanism to prevent concurrent fetches of the same key
# Note: This only works within a single process; for multi-process deployment,
# a distributed lock would be needed (e.g., Redis-based)
_pending_fetches = {}
_pending_fetches_lock = threading.Lock()


def _write_cache_file(cache_file: Path, payload) -> None:
    """Write the day cache to disk and keep the size estimate in sync."""
    global _cache_size_estimate
    try:
        previous_size = cache_file.stat().st_size
    except OSError:
        previous_size = 0
    with open(cache_file, "wb") as f:
        pickle.dump(payload, f)
    try:
        _cache_size_estimate += cache_file.stat().st_size - previous_size
    except OSError:
        pass


def _enforce_cache_size_limit(force: bool = False) -> None:
    """Evict the least recently written cache files to stay within the size limit.

    This is a no-op when the limit is disabled (MAX_CACHE_SIZE_MB <= 0), which is
    the default outside Render: a development machine must never silently delete
    market data that was just downloaded.
    """
    global _last_enforcement_time, _cache_size_estimate

    if not CACHE_EVICTION_ENABLED:
        return

    now = time.monotonic()
    if not force and (now - _last_enforcement_time) < _ENFORCE_INTERVAL_SECONDS:
        # A scan is due shortly. Only scan early when the cache is already over
        # the limit, so the size stays bounded.
        if _cache_size_estimate < MAX_CACHE_SIZE_BYTES:
            return

    _last_enforcement_time = now

    try:
        # Collect cache files with their size and last write time
        cache_files = []
        for cache_file in CACHE_DIR.glob("*.pkl"):
            try:
                stat = cache_file.stat()
                cache_files.append((cache_file, stat.st_mtime, stat.st_size))
            except OSError:
                # Skip files that can't be accessed
                continue

        # Least recently written first. Modification time is used rather than
        # access time because access times are unreliable across filesystems and
        # are frequently not updated at all.
        cache_files.sort(key=lambda item: (item[1], item[0].name))

        # Calculate total size
        total_size = sum(size for _, _, size in cache_files)

        evicted = 0
        freed_bytes = 0

        # Remove oldest files until we're under the limit. The most recently
        # written file is never removed: it is the work that was just done and
        # the one most likely to still be needed.
        while total_size > MAX_CACHE_SIZE_BYTES and len(cache_files) > 1:
            oldest_file, _, file_size = cache_files.pop(0)
            try:
                os.remove(oldest_file)
                total_size -= file_size
                freed_bytes += file_size
                evicted += 1
            except OSError as e:
                print(f"Error removing cache file {oldest_file.name}: {e}")

        _cache_size_estimate = total_size

        if evicted:
            limit_mb = MAX_CACHE_SIZE_BYTES / (1024 * 1024)
            print(
                f"Evicted {evicted} cache file(s), freed "
                f"{freed_bytes / (1024 * 1024):.1f} MB to stay within the "
                f"{limit_mb:.0f} MB local cache limit "
                f"(now {total_size / (1024 * 1024):.1f} MB)"
            )

    except Exception as e:
        print(f"Error enforcing cache size limit: {e}")


def get_cache_stats():
    """Get statistics about the local cache."""
    try:
        cache_files = list(CACHE_DIR.glob("*.pkl"))
        file_count = len(cache_files)
        
        total_size = 0
        access_times = []
        for cache_file in cache_files:
            try:
                file_size = os.path.getsize(cache_file)
                access_time = os.path.getatime(cache_file)
                total_size += file_size
                access_times.append(access_time)
            except OSError:
                # Skip files that can't be accessed
                continue
        
        avg_access_time = sum(access_times) / len(access_times) if access_times else 0
        
        with _memory_cache_lock:
            memory_cache_size = len(_memory_cache)
        
        return {
            "file_count": file_count,
            "total_size_bytes": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "max_cache_size_mb": MAX_CACHE_SIZE_MB,
            # 0 means unlimited: no cache file is ever deleted.
            "cache_eviction_enabled": CACHE_EVICTION_ENABLED,
            "cache_usage_ratio": (
                total_size / MAX_CACHE_SIZE_BYTES if MAX_CACHE_SIZE_BYTES > 0 else None
            ),
            "memory_cache_items": memory_cache_size,
            "max_memory_cache_items": _MAX_MEMORY_CACHE_ITEMS,
            "oldest_file_access": min(access_times) if access_times else None,
            "newest_file_access": max(access_times) if access_times else None,
        }
    except Exception as e:
        print(f"Error getting cache stats: {e}")
        return {}


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
    cache_file = CACHE_DIR / cache_file_name(day_key)
    r2_key = f"{R2_KEY_PREFIX}/{cache_file_name(day_key)}"
    cache_key = f"{day_key}:{instrument_key}"  # Unique key for this instrument/date combination

    # Check in-memory cache first to avoid repeated deserialization
    with _memory_cache_lock:
        if cache_key in _memory_cache:
            # Move to end (most recently used)
            result = _memory_cache.pop(cache_key)
            _memory_cache[cache_key] = result
            return result

    # Check if there's already a fetch in progress for this key (to prevent duplicate fetches)
    fetch_lock = None
    with _pending_fetches_lock:
        if cache_key in _pending_fetches:
            fetch_lock = _pending_fetches[cache_key]
        else:
            fetch_lock = threading.Lock()
            _pending_fetches[cache_key] = fetch_lock
    
    # If another thread is already fetching this key, wait for it
    if fetch_lock.locked():
        # Wait for the in-progress fetch to complete
        fetch_lock.acquire()
        fetch_lock.release()
        # After waiting, check memory cache again (the other thread should have populated it)
        with _memory_cache_lock:
            if cache_key in _memory_cache:
                result = _memory_cache.pop(cache_key)
                _memory_cache[cache_key] = result
                return result
        # Fall through to normal processing if still not in cache
    
    # We're responsible for fetching this data
    try:
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
            result = day_cache[instrument_key]
            # Store in memory cache for future quick access
            with _memory_cache_lock:
                _memory_cache[cache_key] = result
                # Enforce memory cache size limit
                if len(_memory_cache) > _MAX_MEMORY_CACHE_ITEMS:
                    _memory_cache.popitem(last=False)  # Remove least recently used
            return result

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
                            _write_cache_file(cache_file, day_cache)
                        except Exception as e:
                            print(f"Error saving day cache file {cache_file}: {e}")
                        
                        result = r2_cache[instrument_key]
                        # Store in memory cache for future quick access
                        with _memory_cache_lock:
                            _memory_cache[cache_key] = result
                            # Enforce memory cache size limit
                            if len(_memory_cache) > _MAX_MEMORY_CACHE_ITEMS:
                                _memory_cache.popitem(last=False)  # Remove least recently used
                        return result
                    # If not in R2 cache, we'll fall through to Upstox
                    else:
                        # Still store the R2 data locally for potential future use
                        if not local_cache_hit:
                            day_cache = r2_cache
                        elif not day_cache:  # Only if we don't have any local data yet
                            day_cache = r2_cache
                        # Save the R2 data locally
                        try:
                            _write_cache_file(cache_file, day_cache)
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
                            volume=row[5],
                            oi=row[6],
                        )
                    )

        result = list(reversed(candles))

        # Update the per‑day cache dict and persist it to both local cache and R2
        day_cache[instrument_key] = result
        try:
            # Save to local cache
            _write_cache_file(cache_file, day_cache)
            # Save to R2
            pickle_data = pickle.dumps(day_cache)
            put_object(R2_BUCKET_NAME, r2_key, pickle_data)

            # Enforce bounded local cache size (evict oldest files if needed).
            # No-op when the limit is disabled, which is the default locally.
            _enforce_cache_size_limit()
        except Exception as e:
            print(f"Error saving day cache file {cache_file}: {e}")

        if not result:
            print(f"No candles found for {instrument_key}. Cached empty result.")

        # Store in memory cache for future quick access
        with _memory_cache_lock:
            _memory_cache[cache_key] = result
            # Enforce memory cache size limit
            if len(_memory_cache) > _MAX_MEMORY_CACHE_ITEMS:
                _memory_cache.popitem(last=False)  # Remove least recently used

        return result
    finally:
        # Remove the pending fetch marker
        with _pending_fetches_lock:
            if cache_key in _pending_fetches:
                del _pending_fetches[cache_key]