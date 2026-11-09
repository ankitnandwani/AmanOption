"""Shared cache key layout.

The application and the migration utility must agree on these names, otherwise
objects written to R2 by the migration are invisible to the running app. Keep
this module free of heavy dependencies so both the service layer and standalone
CLI tools can import it.
"""

import os
from pathlib import Path

# Local cache directory name, relative to the project root.
CACHE_DIR_NAME = "historical_cache"

# Object key prefix used for every cached day in R2.
R2_KEY_PREFIX = os.getenv("R2_KEY_PREFIX", CACHE_DIR_NAME)

# Extension of a cache file.
CACHE_FILE_SUFFIX = ".pkl"


def local_cache_dir() -> Path:
    """Return the local cache directory."""
    return Path(CACHE_DIR_NAME)


def cache_file_name(day_key: str) -> str:
    """Return the cache file name for a day key (``YYYY-MM-DD`` or ``from_to``)."""
    return f"{day_key}{CACHE_FILE_SUFFIX}"


def r2_object_key(day_key: str, prefix: str = None) -> str:
    """Return the R2 object key for a day key.

    Example: ``historical_cache/2024-01-15.pkl``. This matches the key layout
    used by ``services.historical_service.get_historical_candles``.
    """
    effective_prefix = R2_KEY_PREFIX if prefix is None else prefix
    effective_prefix = (effective_prefix or "").strip("/")
    file_name = cache_file_name(day_key)
    if not effective_prefix:
        return file_name
    return f"{effective_prefix}/{file_name}"
