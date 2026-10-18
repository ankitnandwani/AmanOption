# AmanOptions — Agent Instructions

Repository: https://github.com/ankitnandwani/AmanOption

## Purpose of this file
This is the entry point for coding agents. Read this file first, then read `docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`, and `docs/DATA_AND_CACHE.md` before making material changes. For cache-migration work, also read the four `docs/cache-migration/` documents.

These documents capture the project context currently known to the owner and assistant. They are not a substitute for validating implementation details against the repository. Do not perform a full-repository scan every session: start with these docs, check Git status, then inspect only the relevant files and tests needed for the assigned task.

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

## Known project context
- Python application called AmanOptions.
- User reports the app is deployed on Render as a Free Web Service.
- The app has a market-data cache, Upstox integration, and single-day / multi-day backtesting functionality.
- The current local machine has `historical_cache/` and `backtest_results/` directories that are absent from GitHub because they contain large data files.
- `historical_cache/` is reported to contain approximately 962 `.pkl` files totalling about 3.14 GB. Existing behavior is date-oriented: use cached data when present; otherwise fetch from Upstox and save for reuse.
- The cache is intended to be shared by all application users.
- Cloudflare R2 is the currently preferred candidate for durable shared cache storage. The design is not yet implemented or verified unless the task tracker says otherwise.
- Render's local filesystem should be treated as ephemeral for a Free Web Service. Use it only as a bounded temporary cache, not as the source of truth.
- Do not assume exact module names, file paths, file naming rules, pickle schema, entry points, or dependencies from this summary. Verify these only in relevant code when needed.

## Cache migration principles
- Keep GitHub for source code and small documentation/configuration files, not the multi-gigabyte data cache.
- Keep R2 private and access it using server-side credentials stored in Render environment variables.
- Never expose R2 credentials in client-side code, logs, screenshots, or committed files.
- Preserve current cache compatibility and backtest results.
- Do not download the entire bucket at application startup.
- Use local caching and backtest-level reuse to avoid repeated network calls.
- Consider concurrency: multiple users may request the same missing date simultaneously.
- Pickle deserialization is unsafe for untrusted or tampered objects. Only load objects from the trusted cache pipeline and consider integrity/metadata checks.
- Before publishing or sharing market data, the owner should confirm Upstox terms permit retention and the intended shared use.

## Task handoff
When switching agents:
1. Read the context docs and the current handoff.
2. Check `git status`.
3. Verify the next task against current code and test evidence.
4. Complete only the next approved task.
5. Update the handoff with changed files, tests, unresolved questions, and the exact next step.
