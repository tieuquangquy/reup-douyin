# Douyin Ready Check Architecture

## Objective

Give the operator one action before `/intake` that answers:

1. which account is usable now,
2. whether the saved browser profile is active or reusable,
3. whether reopen is needed,
4. which fetch path will be used,
5. whether it is safe to run intake now.

## No-Duplication Strategy

Ready Check is an aggregation layer over existing canonical logic:

- account selection from `IntakeDiscoveryService`,
- account health from `DouyinAccountService.health_summary()`,
- runtime liveness from `DouyinBrowserContextRegistry.watchdog_for_account()`,
- readiness/path selection from `DouyinAccountService.preflight_fetch_readiness()`.

It does not ingest profiles, discover videos, or create a second fetch pipeline.

## Result Categories

- `READY`
  - usable account
  - browser-profile path ready now
  - safe to run intake now
- `READY_AFTER_REOPEN`
  - browser-profile path is the intended path
  - saved profile is not active now
  - reopen is required before intake
- `FALLBACK_READY`
  - browser-primary path is unavailable
  - fallback is allowed and usable
  - intake can run under fallback conditions
- `NOT_READY`
  - no usable account/profile/fallback path
  - action is required before intake

## Input Signals

- requested account id
- resolved account id
- account selection mode/reason
- account health status
- preflight cache reuse flag
- watchdog result/status/reason
- browser profile availability
- browser reopen need/result
- selected fetch path
- fallback allowed policy

## UI Behavior

`/intake` adds a `Ready Check` action and compact result card.

The card shows:

- selected or recommended account,
- browser profile status,
- whether reopen is needed,
- intended fetch path,
- concise summary,
- recommended next action.

## Canonical Pipeline Unchanged

Ready Check runs before intake discovery and does not change:

```text
DouyinProfileAdapter
  -> SourceIngestService
  -> SourceProfile / SourceVideo / CrawlSession / VideoMetricSnapshot
  -> CandidateEvaluationService
```
