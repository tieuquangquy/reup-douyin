# Douyin Browser Primary Fetch Architecture

## Objective

For connected Douyin accounts in local development, browser-profile-backed fetch is the default primary execution path. HTTP fetch is secondary fallback only.

## Browser-Primary Selection Rules

Browser-primary mode applies when:

- the fetch is account-backed through `DouyinAccountService`,
- the live fetch client receives a browser fetch callback,
- `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true`.

Under the repo defaults, these conditions are true for connected-account `/intake` discovery.

## HTTP Fallback Rules

HTTP fallback is allowed when browser-profile fetch cannot run because:

- persistent browser profile is missing,
- browser runtime is unavailable,
- browser context is stale/closed/unrecoverable for the current run,
- browser-profile-backed fetch reports `browser_profile_unavailable` or `browser_context_unavailable`.

HTTP fallback is not used to hide browser-profile classified failures such as:

- challenge/blocked response,
- login required,
- parse-zero browser profile result.

Those are explicit failures because retrying HTTP would usually reintroduce the shell/challenge ambiguity.

## Observability Fields

Fetch metadata should make the strategy obvious:

- `strategy_policy = browser_primary`
- `primary_execution_path = browser_profile`
- `fetch_execution_path`
- `final_execution_path_used`
- `http_fallback_attempted`
- `browser_profile_available`
- `browser_profile_unavailable_reason`

These fields are now propagated into crawl-session raw summaries, fetch observability, `/intake` response schemas, and the Intake status panel.

## Canonical Pipeline Unchanged

Only raw fetch transport selection changes. The output still flows through:

```text
DouyinProfileAdapter.normalize_fetch_payload()
  -> SourceIngestService.ingest_profile()
  -> SourceProfile / SourceVideo / CrawlSession / VideoMetricSnapshot
  -> CandidateEvaluationService
```

No second persistence path or browser-only candidate pipeline exists.

## Remaining Limits

- Browser profile fetch can still hit a Douyin challenge page.
- HTTP fallback can still return shell/challenge responses if no browser profile is usable.
- Real success requires a valid logged-in persistent browser profile.
