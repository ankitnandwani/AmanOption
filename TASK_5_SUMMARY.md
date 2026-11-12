# Task 5 — Resumable Migration Utility: Implementation Summary

## Overview
Rewrote `migrate_cache_to_r2.py` as a resumable, verifiable migration utility for moving the
local `historical_cache/` into a private Cloudflare R2 bucket, and closed a key-layout defect
that would have made every migrated object invisible to the running application.

## Defect found and fixed

The previous utility uploaded local file `2025-04-04.pkl` under the object key `2025-04-04.pkl`,
but the application reads and writes `historical_cache/2025-04-04.pkl`
(`services/historical_service.py`). Every migrated object would have been silently unreachable
at runtime, and the migration would have appeared to succeed.

The layout is now defined once in `services/cache_keys.py` and consumed by both the service layer
and the migration tool, so the two cannot drift apart again. The generated key string is
unchanged for the application (`historical_cache/{day_key}.pkl`), so existing behaviour and the
existing unit-test expectations are preserved.

## Features implemented

### 1. Correct key layout
- `services/cache_keys.py` is the single source of truth: `R2_KEY_PREFIX`, `cache_file_name()`,
  `r2_object_key()`.
- `services/historical_service.py` builds its R2 key from that module.
- `migrate_cache_to_r2.py` builds object keys with the same helper.
- A unit test asserts the tool's key equals the application's key for the same day.

### 2. Four operating modes
| Mode | Purpose | Writes to R2 |
|---|---|---|
| `--list` | Inventory the local cache and compare against R2 | No |
| `--dry-run` | Print the planned actions (upload / skip / replace) | No |
| `--upload` | Upload missing objects (default action) | Yes |
| `--verify` | Verify object count, bytes, sizes and checksums | No |

`--list` works without credentials. The other modes fail with an explicit message when the
bucket or the credentials are missing, instead of failing silently.

### 3. Resume and retry
- Uploads are idempotent: an object that already exists with the expected size is skipped.
- A local state file (`migration_state.json`, git-ignored) records per-file status, size,
  MD5, SHA-256, attempt count and timestamp. The file is rewritten after every file, so an
  interrupted run resumes exactly where it stopped.
- On resume, a file recorded as uploaded is confirmed against R2 before being skipped.
- `--force` re-uploads everything; `--retries` / `--backoff` control retry behaviour with
  exponential backoff (default 3 retries, 2s base).
- Failed files are recorded, the run continues, and the process exits non-zero.

### 4. Verification of count, bytes and checksums
- `--verify` lists the objects under the prefix and compares object count, total bytes and
  per-object size against the local cache.
- Checksums are computed locally (MD5 and SHA-256) and stored as R2 object metadata at upload
  time. Verification compares the stored MD5 with the local MD5. When an object has no
  metadata, a plain-MD5 ETag is accepted as a fallback; multipart ETags are correctly treated
  as unverifiable rather than as a mismatch.
- The report lists missing objects, size mismatches, checksum mismatches and extra objects,
  and exits non-zero on any problem.

### 5. Local files are never modified or deleted
- The tool only reads the cache directory. There is no delete, unlink or remove call anywhere
  in it; a unit test asserts the absence of every destructive API.
- A second test runs a full upload and confirms the source files still exist with byte-identical
  content afterwards.

### 6. R2 adapter additions (`services/r2_service.py`)
- `put_file()` — managed, streaming upload, so large pickles are not buffered in memory.
  Falls back to a buffered upload if the client lacks the managed transfer helpers.
- `head_object()` — object size, ETag and user metadata.
- `list_objects()` — paginated listing under a prefix.
- `put_object()` — optional `metadata` argument. When it is omitted the request is unchanged,
  so existing call sites and their unit tests are unaffected.
- The client now sets `request_checksum_calculation="when_required"`. Recent botocore versions
  attach a CRC32 `ChecksumAlgorithm` to every `PutObject` by default, which Cloudflare R2 does
  not reliably accept. Older botocore versions without the option are handled.

## Files changed
- `migrate_cache_to_r2.py` — rewritten (modes, resume, retry, verification, checksums).
- `services/cache_keys.py` — **new**; shared cache key layout.
- `services/r2_service.py` — `put_file`, `head_object`, `list_objects`, optional metadata,
  R2-compatible checksum configuration.
- `services/historical_service.py` — R2 key now built from `services/cache_keys`. Generated
  key is unchanged.
- `tests/test_migrate_cache_to_r2.py` — **new**; 22 tests for the migration utility.
- `tests/test_r2_service.py` — 4 new API-contract tests; updated client-construction assertion.
- `tests/test_historical_service.py` — safety fix (see below).
- `.gitignore` — **new**; ignores `migration_state.json`, `__pycache__`, `.DS_Store`.

## Data-loss hazard found and fixed (outside Task 5, required to run tests safely)

Running the test suite deleted **all 108 files (496 MB)** from `historical_cache/`. Cause:

- `tests/test_historical_service.py` never redirected the cache directory, so
  `get_historical_candles()` wrote to and then evicted from the **real** `historical_cache/`.
- `tests/test_cache_efficiency.py` and `tests/test_task4_verification.py` set
  `MAX_CACHE_SIZE_MB=1` in the environment before `services.historical_service` is imported, so
  the module-level `MAX_CACHE_SIZE_BYTES` was 1 MB for the whole test process.
- The eviction helper therefore removed real files until the 496 MB cache fitted under 1 MB.

The files were recovered intact from the Git index (`git ls-files | git checkout-index -f --stdin`);
all 108 files were restored byte-for-byte. The test now points `CACHE_DIR` at a temporary
directory and disables eviction, so the suite can never touch real cache data again. Verified:
the cache is 108 files / 496 MB both before and after a full test run.

## Testing
- `tests/test_migrate_cache_to_r2.py`: 22 tests, all pass.
- `tests/test_r2_service.py`: 15 tests (11 existing + 4 new API-contract tests), all pass.
- Full suite: 47 tests, 41 pass, **5 failures + 1 error that are identical to the pre-existing
  baseline** (see "Known limitations" in the handoff).
- An end-to-end run was performed through the real botocore code path with a stubbed transport:
  upload wrote the expected keys and checksum metadata, `--verify` reported count match, byte
  match and 2/2 checksums verified (PASS), and the local files were unchanged.

## Not done in this task
- No live upload to R2 was performed: no R2 credentials are available in this environment.
  The utility must be run by the owner with `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY` and the target bucket.
- `backtest_results/` was not touched.

## Usage
```bash
export R2_ENDPOINT="https://<account_id>.r2.cloudflarestorage.com"
export R2_ACCESS_KEY_ID="..."
export R2_SECRET_ACCESS_KEY="..."
export R2_BUCKET_NAME="amanoptions-historical-cache"

python migrate_cache_to_r2.py --list        # inventory
python migrate_cache_to_r2.py --dry-run     # planned actions
python migrate_cache_to_r2.py --upload      # resumable upload
python migrate_cache_to_r2.py --verify      # count / bytes / checksum verification
```

## Backward compatibility
- The application's R2 key and local cache file layout are unchanged.
- `put_object()` keeps its original signature and request shape when no metadata is supplied.
- No strategy, P&L, UI or backtest code was modified.
