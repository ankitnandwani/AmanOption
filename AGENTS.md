# AmanOptions — Agent Instructions

Repository: https://github.com/ankitnandwani/AmanOption

## Purpose of this file
This is the entry point for coding agents. Read this file first, then `docs/PROJECT_CONTEXT.md`,
`docs/ARCHITECTURE.md`, and `docs/DATA_AND_CACHE.md`. For cache-migration work, also read the four
`docs/cache-migration/` documents.

These documents capture the context known to the owner and assistant. They are not a substitute for
validating implementation details against the repository. Do not perform a full-repository scan
every session: start with these docs, check Git status, then inspect only the files and tests
needed for the assigned task.

## The goal
AmanOptions is a NiceGUI app for options-strategy backtesting. It is deployed on Render Free Web
Service and must stay usable by any visitor with minimal friction.

The market data is the expensive part: Upstox's historical availability is limited, so the same
data must be served to every visitor from one shared copy. **Cloudflare R2 is that shared copy.**
The local cache is a temporary working copy, never the source of truth.

Current focus: finish the cache migration so the app serves its data from R2 and stops depending
on the Upstox API for any day already stored.

## Working state (read first — not committed)
- `HEAD` is `b51b339` ("task5"). **The Task 5 migration work and the cache-eviction fix are complete
  but uncommitted in the working tree.** Check `git status` before starting; do not discard them.
- Uncommitted changes: `migrate_cache_to_r2.py`, `services/cache_keys.py` (new), `services/r2_service.py`,
  `services/historical_service.py`, `tests/test_migrate_cache_to_r2.py` (new),
  `tests/test_cache_eviction_policy.py` (new), `tests/test_r2_service.py`,
  `tests/test_historical_service.py`, `.gitignore` (new), and the docs.
- The staged `historical_cache/` and `backtest_results/` files are a partial in-repo snapshot, not
  source. The owner keeps the authoritative full backup of the dataset separately. Do not commit
  these data files and do not unstage them without approval.

## What has been built
- **R2 adapter** (`services/r2_service.py`): `get_client`, `object_exists`, `get_object`,
  `put_object` (optional metadata), `put_file` (managed streaming upload), `head_object`,
  `list_objects` (paginated). Unit-tested plus 4 tests against the real botocore API contract.
- **App read path**: local → R2 → Upstox. **Write path**: every fetched day goes to local *and* R2.
- **Shared key layout** (`services/cache_keys.py`): the single source of truth for the local file
  name and the R2 object key, imported by both the service layer and the migration tool so they
  cannot drift apart. Local file and R2 key are both `historical_cache/{day_key}.pkl`; `day_key` is
  `YYYY-MM-DD` or `from_date_to_date` for a range.
- **Migration utility** (`migrate_cache_to_r2.py`): resumable, retrying, verifiable, and it never
  modifies or deletes the local files.

## Current task
The cache migration and Task 8 cutover review are complete. R2 is the shared
historical cache. Keep the local originals and staged recovery snapshot until
explicit owner approval to remove them. Backtest history stays on the current
filesystem. See the handoff for the two optional R2 cleanup candidates.
See `docs/cache-migration/CACHE_MIGRATION_TASKS.md` and the handoff for the verified
bucket, settings, and deployment checks.

## Running the migration
```bash
export R2_ENDPOINT=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET_NAME=...
python migrate_cache_to_r2.py --list      # inventory local vs R2 (works without credentials)
python migrate_cache_to_r2.py --dry-run   # planned actions, no writes
python migrate_cache_to_r2.py --upload    # resumable upload
python migrate_cache_to_r2.py --verify    # count / bytes / size / checksum verification
```
- Resumable via `migration_state.json` (git-ignored), rewritten after every file. `--force`
  re-uploads; `--retries`/`--backoff` control retries.
- MD5/SHA-256 are stored as object metadata, so verification does not depend on the ETag (multipart
  ETags are not MD5s).
- The bucket is `R2_BUCKET_NAME` (default `amanoptions-historical-cache`); `R2_BUCKET` is also
  accepted. Credentials: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
- At this dataset size everything fits inside R2's free tier (10 GB-month storage, 1M Class A
  writes, 10M Class B reads) and egress is free, so the migration and the running app cost $0.

## Guardrails
- **Never let the app delete locally downloaded market data.** The bounded cache exists only to
  protect Render's small ephemeral disk. `MAX_CACHE_SIZE_MB` (read once at import) is unlimited
  outside Render and 500 MB on Render (detected via `RENDER=true`); `0` or negative means
  unlimited and must never mean "delete everything". A global cap once deleted the owner's 2024
  data — do not re-introduce one.
- **Tests must never point the cache layer at the real `historical_cache/`.**
  `_enforce_cache_size_limit()` deletes real files. Tests redirect `CACHE_DIR` to a temp path.
- Keep R2 private and access it with server-side credentials in Render environment variables.
  Never expose credentials in client code, logs, screenshots, or committed files.
- Keep GitHub for source and small docs, not the multi-gigabyte data cache.
- Do not download the whole bucket at application startup.
- Pickle deserialization is unsafe for untrusted objects — only load from the trusted pipeline and
  keep the bucket write-restricted.
- Upstox terms on retaining and sharing market data are still unconfirmed; the owner owns that
  decision.

## Design caveats worth knowing before changing the cache
- One R2 object per day, holding ~211 instruments. The app downloads a day object once and serves
  the other contracts from the local cache, so a full backtest costs ~1013 GETs, not ~211,000. But
  adding a new contract to a day re-uploads the whole day object, so migrate complete days.
- Non-trading days are cached as empty on purpose and the app treats empty as a hit, so a day
  downloaded during an API hiccup stays empty permanently. `--verify` detects truncated uploads
  but cannot tell "genuinely empty" from "the API returned nothing".
- Two visitors fetching different contracts for the same day can race on the read-modify-write of
  the day object; the last write wins and one contract's entry can be dropped, costing at most one
  extra Upstox fetch.

## Testing
- `.venv/bin/python -m unittest discover -s tests` (58 tests, ~8s).
- **5 failures + 1 error are pre-existing and expected.** They are Task 4 test-harness defects:
  `tests/test_cache_efficiency.py` and `tests/test_task4_verification.py` patch
  `services.r2_service.get_object` and `services.upstox_service.get_expired_historical_candles`,
  but `services/historical_service` imports those names directly, so the patches never apply. The
  fix is to patch the *importing* module (`services.historical_service`) instead.
- Everything else passes: 22 migration-tool tests, 11 eviction-policy tests, 15 R2 adapter tests.

## Project safety and workflow
- Preserve existing behavior unless the task explicitly changes it.
- Do not rewrite unrelated modules or refactor the whole application as part of a focused task.
- Before editing, state the task, intended changes, and acceptance criteria.
- Work in small, reviewable tasks. Do not silently continue into the next task.
- Prefer the project's existing patterns, dependency manager, formatting, and testing conventions.
- Check `git status` before editing. Never overwrite or discard uncommitted user changes.
- Do not commit secrets, credentials, tokens, local environment files, or large market-data/backtest datasets.
- Do not delete, rename, or bulk-move `historical_cache/`, `backtest_results/`, or other data directories without explicit approval.
- Never claim tests passed unless they were run and passed. If tests cannot be run, explain why.
- At the end of a task, update the relevant docs and `docs/cache-migration/CACHE_MIGRATION_HANDOFF.md` when the task concerns cache migration.

## Task handoff
When switching agents:
1. Read the context docs and the current handoff.
2. Check `git status`.
3. Verify the next task against current code and test evidence.
4. Complete only the next approved task.
5. Update the handoff with changed files, tests, unresolved questions, and the exact next step.
