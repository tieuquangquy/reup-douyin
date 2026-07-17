# Douyin Profile Quarantine Architecture

## Purpose

Douyin sometimes allows a browser-backed profile to be casually viewable while automation-assisted validation, capture, or Intake repeatedly hits security challenges. The quarantine feature separates such profiles from the primary happy path without destroying their saved profile data.

The result is an operational safety layer:

- risky profiles are retained for reference and troubleshooting;
- normal recommendation/Ready Check/Intake/capture stop preferring them;
- the operator is guided toward creating or using a cleaner managed browser profile.

## Boundary Rules

This feature does not change the canonical account or downstream discovery architecture:

- `DouyinAccountConnection` remains the source account connection model.
- One Douyin account remains mapped to one managed persistent browser profile.
- `SourceProfile`, `SourceVideo`, `CrawlSession`, `VideoMetricSnapshot`, and `VideoCandidate` remain the downstream pipeline.
- Quarantine is not a delete operation.
- Quarantine is not a crawler, scorer, queue, or publishing implementation.

## State Model

Quarantine state is stored in account metadata for Phase 1 to avoid an unnecessary schema migration while the policy is still local-first.

Persisted metadata keys:

- `douyin_profile_quarantine_state`
- `douyin_profile_quarantine_reason`
- `douyin_profile_quarantine_detected_at`
- `douyin_profile_quarantine_recommended_next_action`
- `douyin_profile_quarantine_challenge_count`
- `douyin_profile_quarantine_blocked_count`
- `douyin_profile_quarantine_replaced_by_account_id`

Canonical states:

| State | Meaning | Primary flow behavior |
| --- | --- | --- |
| `active_preferred` | Healthy enough for normal operation | Can be recommended and used |
| `active_warning` | Some risk evidence below threshold | Can be used, warning shown |
| `quarantine_candidate` | Threshold has been crossed or is about to be crossed | Should not be preferred |
| `quarantined` | Profile is operationally quarantined | Block normal Intake/capture |
| `quarantined_recoverable` | Quarantined but still openable and inspectable | Block normal Intake/capture, allow reference |
| `quarantined_replaced` | Quarantined and another account is preferred | Block normal Intake/capture |

## Detection Inputs

The policy reads only non-secret operational metadata:

- challenge state
- challenge count
- blocked browser-context count
- last browser validation categories
- post-challenge recheck result
- saved profile presence

No raw cookies, tokens, credentials, or private local paths are logged or exposed.

## Deterministic Quarantine Policy

A browser-backed account/profile is quarantined when it has a saved browser profile and one or more of these conditions is true:

1. `douyin_challenge_state == "challenge_repeat_limit_reached"`
2. `douyin_challenge_count >= 3`
3. `browser_context_blocked_count >= 3`
4. post-challenge recheck repeatedly still requires challenge resolution while challenge count is at or above the repeat threshold.

A profile can be projected as `active_warning` when it has challenge evidence below threshold, such as one or two challenge detections or a browser-context blocked count below the quarantine threshold.

## Transitions

### Normal to warning

A profile moves from `active_preferred` to `active_warning` when low-level challenge evidence is present but thresholds are not crossed.

### Warning to quarantine

A profile moves to `quarantined_recoverable` when the deterministic threshold is crossed.

### Quarantine replacement

When a clean account exists and the quarantined account is not the preferred account, the quarantined account can be projected as `quarantined_replaced` or include a replacement account id if one is known.

### Recovery

Recovery is intentionally conservative. Successful validation may clear transient challenge metadata, but quarantine should not be silently removed by casual browsing. If recovery is added in this step, it should require strong browser-backed validation and should keep an audit marker that the profile was previously quarantined.

## Backend Integration

### Health projection

`DouyinAccountService.health_summary` is the central gate for `can_use_for_live_fetch`. Quarantined profiles should return blocked/unusable health with a quarantine reason.

### Preflight readiness

`DouyinAccountService.preflight_fetch_readiness` should return a dedicated blocked preflight result for quarantined profiles before attempting browser reopen/fetch.

Expected values:

- `preflight_result = "failed"`
- `fetch_readiness_category = "fetch_blocked_by_profile_quarantine"`
- `preflight_failure_code = "profile_quarantined"`
- `preflight_failure_message` recommends using a clean managed browser profile.

### Account recommendation

`IntakeDiscoveryService._resolve_live_fetch_account_selection` already selects by `health.can_use_for_live_fetch`. Once quarantine health returns unusable, default and fallback recommendation should naturally skip quarantined profiles. The selected-account path should provide explicit quarantine messaging.

### Ready Check

Ready Check should map quarantine preflight to a dedicated status:

- `PROFILE_QUARANTINED`

Recommended action:

- `create_clean_browser_profile`

### Current-page capture

Detection remains allowed for reference because it only inspects the live page. Capture is a normal operational action and should be blocked for quarantined profiles unless a future explicit override is designed.

## Frontend Integration

### Accounts page

The Douyin accounts UI should:

- show quarantine status, reason, and recommended action;
- keep Open/Reopen available;
- keep Detect current page available for reference when runtime is active;
- disable or warning-gate Use in Intake and Capture current page;
- show clean-profile recommendation copy.

### Intake page

The Intake selector should:

- not auto-select quarantined accounts;
- disable quarantined accounts in the select list;
- explain that the operator should create/use a clean managed browser profile;
- show Ready Check `PROFILE_QUARANTINED` distinctly from generic `NOT_READY`.

## Observability

Logs should include stable identifiers only:

- account id
- diagnostics id
- state/reason/category
- counts

Logs must not include raw cookies, credentials, or private browser-profile paths.
