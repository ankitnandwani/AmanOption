# Cloud backtest history tasks

Use `[ ]` for pending, `[~]` for in progress, and `[x]` for complete. Record evidence
in the handoff and stop for review after each task.

- [x] **Task 1 — Persist completed reports**
  - Implement the versioned JSON report and private R2 storage service. Wire it into
    the existing multi-day completion path behind the feature flag. Preserve local
    output, result rendering, and failure reporting.
  - Test field allowlisting, legacy local JSON, independent IDs for simultaneous
    jobs, retry of the same key, and successful result delivery when upload fails.
  - 57 targeted tests passed. A two-client NiceGUI check verified completion
    isolation, rendering after an upload failure, and the legacy history reader.
- [x] **Task 2 — Read cloud history in the UI**
  - Extend the existing View History button with newest-first pages and lazy report
    details. Reuse the current summary and daily P&L renderer.
  - Verify loading, empty and unavailable states, malformed and missing reports,
    continuation across pages, local mode, and independent browser sessions. Check
    that viewing history calls neither the strategy engine nor Upstox.
  - 60 targeted tests passed. A two-client NiceGUI check with mocked cloud reads
    verified the history controls, result rendering, errors, and the local path.
- [ ] **Task 3 — Validate and deploy**
  - Confirm the production audience and report fields, then enable cloud history
    only with the approved visibility model. Verify the configured R2 bucket and
    prefix with a synthetic report before publishing real reports.
  - Deploy a source-only revision to Render. Run a multi-day backtest, open the
    result from a fresh browser, and verify it survives a restart or redeploy.
    Compare displayed daily and total P&L and record rollback steps.

Next task when implementation is requested: **Task 3**. Existing-report import
is outside these tasks and requires a separate scope and review.
