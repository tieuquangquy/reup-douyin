# Douyin Browser Watchdog Architecture

## Objective

Reduce local-dev friction around persistent Douyin browser profiles without changing the canonical account, fetch, ingest, or candidate pipeline.

## Watchdog Model

The watchdog is a runtime support layer owned by `DouyinBrowserContextRegistry`.

It answers:

- is there a runtime context for this account?
- is it active and healthy enough to reuse?
- did the registry reconcile stale/invalid runtime state while checking?
- why is the runtime unavailable if it is not reusable?

The watchdog does not validate Douyin account health or fetch profile videos. It only checks browser-profile runtime liveness and usability hints.

## Self-Healing Rules

The watchdog reuses the registry's existing `_ensure_usable()` checks:

- active context with readable cookies remains active,
- idle timeout closes the context and reports stale,
- max lifetime closes the context and reports stale,
- lost Playwright context is marked invalid and removed from the runtime registry,
- missing runtime context reports missing.

It does not mark blocked/invalid Douyin accounts as healthy, and it does not hide explicit account health failures.

## Preflight Cache Model

`DouyinAccountService` keeps an in-memory, short-lived cache per account id.

Cached value:

- last passed preflight result,
- selected fetch path,
- browser availability summary,
- watchdog summary,
- timestamp.

Default TTL: 30 seconds.

Only passed preflight results are cached. Failed results are not cached so recovery actions can take effect immediately.

## Invalidation Policy

Preflight cache is invalidated when account state changes through canonical account service actions:

- account update,
- account validation,
- account disable,
- account delete,
- account creation after validation.

Runtime reset/delete flows should also invalidate or naturally bypass stale cache once they route through account state changes.

## Intake Integration

`/intake` preflight sequence becomes:

```text
resolve account
  -> reject blocked/disabled/invalid account health
  -> use recent passed preflight cache if still valid
  -> run browser-profile watchdog
  -> use active browser profile, or auto reopen once, or HTTP fallback
  -> run canonical live fetch / ingest
```

The downstream canonical pipeline remains unchanged:

```text
DouyinProfileAdapter
  -> SourceIngestService
  -> SourceProfile / SourceVideo / CrawlSession / VideoMetricSnapshot
  -> CandidateEvaluationService
```

## Operator-Visible Diagnostics

API/UI may show:

- `preflight_cached`,
- `watchdog_result`,
- `watchdog_status`,
- `watchdog_reason`,
- `runtime_reconciled`.

These are safe operational summaries and do not expose cookies, profile paths, or secrets.

## Remaining Limits

- The watchdog cannot prove that Douyin will not challenge the actual profile page.
- The cache is process-local and disappears on API restart.
- Browser profile availability still depends on local Playwright/browser runtime health.
