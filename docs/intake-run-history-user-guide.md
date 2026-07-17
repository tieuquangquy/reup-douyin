# intake-run-history-user-guide.md

## Purpose
Use `/intake` to quickly inspect recent runs, compare two runs, and diagnose failed fetches without leaving the intake workflow.

## What You Can Do
- View recent intake runs in the side panel.
- Select one run to see deterministic troubleshooting guidance.
- Compare two runs to understand what changed.
- Reuse a prior run source URL to prefill the intake form.

## Run History Panel
1. Open `/intake`.
2. In **Intake run history**, review each run card:
   - profile identifier
   - run status
   - fetch mode
   - matched candidates
   - error code (if any)
3. Click **View details** to load troubleshooting for that run.
4. Click **Reuse source** to prefill the current intake form with that run's submitted profile URL.

## Troubleshooting Panel
When a run is selected, the panel shows:
- category
- severity
- why this classification was selected
- recommended actions

### Categories Used (Deterministic)
- `NO_FAILURE`
- `ACCOUNT_UNUSABLE`
- `AUTH_EXPIRED`
- `PROFILE_NOT_FOUND_OR_PRIVATE`
- `RATE_LIMIT_OR_ANTIBOT`
- `NETWORK_OR_TIMEOUT`
- `UNKNOWN_FAILURE`

These categories are derived from persisted crawl-session signals (`status`, `error_code`, `error_message`, and metadata). They are not manually curated per run.

## Compare Runs Panel
1. Pick a **Left run** and **Right run**.
2. Review deltas:
   - status changed
   - duration delta
   - videos discovered delta
   - matched candidates delta
3. If the same run is selected on both sides, comparison is suppressed until two different runs are selected.

## Fast Operator Workflow
1. Select a failed run in history.
2. Read troubleshooting category and recommended actions.
3. Use **Reuse source**.
4. Adjust account selection / force live refresh / filters as recommended.
5. Re-run discovery and validate new compare deltas.

## Notes and Boundaries
- Run history is read-only and based on canonical `CrawlSession` data.
- No separate run-history table is introduced.
- Quick actions prefill form fields only; they do not trigger hidden retries.
- If account-related failures recur, use `/accounts/douyin` to validate or reconnect account sessions.
