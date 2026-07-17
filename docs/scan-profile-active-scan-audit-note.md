# Scan Profile Active-Scan Audit Note

## Scope

This note records the pre-change audit hypothesis for the authenticated Scan Profile path in `apps/extension-douyin-capture`. It is intentionally limited to scan-path mapping, safety-test targets, and Phase 2 quarantine planning. It does not authorize broad deletion in this phase.

## Suspected Conflicting Paths

1. Canonical active profile-post scanning is the desired authority for authenticated profile scans. The active path discovers a real same-origin `/aweme/v1/web/aweme/post/` request template, warms it up if needed, fetches pages, and finalizes only when active fetch evidence and expected-count completeness agree.

2. Synthetic fallback template creation is useful only as diagnostic evidence. It can mention the profile-post endpoint path and required keys, but it must not be treated as a real request template because it has no source request URL and cannot preserve Douyin anti-bot query context. If this path reports `template_ready_initial`, it can mask the actual failure where the page saw profile-post traffic but the extension failed to capture the real source URL.

3. Passive network probe evidence is currently stronger than DOM evidence for active startup. A probe batch that saw `/aweme/v1/web/aweme/post/` proves endpoint activity, but without bridged `request_url` it is not enough to actively paginate. The correct failure class is `profile_post_endpoint_seen_but_source_url_missing`, not DOM-only success.

4. DOM-only queue builders remain useful as emergency diagnostics and small fallback evidence, but under a known large expected count they can create partial queues that look operationally successful. In the reported shape, `expected=995` and DOM queue around `44` must remain incomplete and keep the primary action at Scan Profile.

5. Legacy scroll scan and DOM finalizer routes can write canonical-looking success state: `profile_scan.status`, `verify.status`, queue entries, queue totals, `layer.profile_scan_ready`, classification status, and diagnostics. These paths can participate in the current bug if they run after active scan failure/no-rounds and overwrite the active incomplete result.

6. Popup/readiness diagnostics can mask the real failure if older fields win over scan-authority diagnostics. Readiness must prefer active-profile-post unresolved states, completeness gates, and large expected-count undercollection over generic `accepted_target_count > 0` or `queue.length >= 20` checks.

7. Backend reconciliation should annotate queue items and counters after a scan result exists; it must not turn DOM-only undercollection into scan readiness or overwrite the active scan failure reason.

## Immediate Safety-Test Targets

- Synthetic fallback templates are never usable and cannot produce `template_ready_initial`.
- DOM-only undercollection with known large expected count is not scan-ready and keeps primary action at Scan Profile.
- Profile-post endpoint seen without source request URL reports the explicit missing-source diagnostic and does not silently succeed through DOM fallback.
- Legacy queue/finalizer paths cannot override a canonical incomplete result.
- Successful active profile-post scans and small-gap active scans remain accepted.

## Non-Goals For This Phase

- No backend/API changes.
- No popup redesign.
- No calibration or collection behavior changes.
- No fake counts or hardcoded profile-specific values.
- No broad deletion until Phase 2 plan is validated by tests.

## Scan Path Audit Map

| Path | Classification | State written | Scan status | Queue total | Readiness | Primary action | Diagnostics | Backend reconciliation | Can participate in current bug |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Active profile-post template discovery and fetch in content script | CANONICAL_KEEP | active fetch diagnostics, active targets, request/page counts, template metadata | yes, through successful active scan result | yes, through active targets and persisted queue | yes, if completeness gate passes | yes, can unlock calibration/collection | yes | no direct backend write | yes, if startup is blocked or diagnostics contradict evidence |
| Passive network probe request URL bridge | CANONICAL_KEEP | passive probe batches, targets, endpoint counters, bridged request URL | no direct status | no direct queue total, but supplies active template evidence | indirect, by allowing active fetch | indirect | yes | no | yes, if endpoint is seen but source URL is missing |
| Synthetic `fallback_unavailable` profile-post template | DIAGNOSTIC_ONLY | template diagnostics only | must not | must not | must not | must not | yes, as unavailable evidence | no | yes, if treated as usable/found/ready |
| DOM active works grid adapter `scan_queue_adapter_22C11B` | UNKNOWN_NEEDS_TEST | DOM target list and adapter diagnostics | should not finalize large-profile success alone | can build visible target count | only when completeness contract permits | may affect action through queue/classification | yes | no | yes, if partial DOM queue masks active failure |
| DOM probe candidate normalizer and queue builder `buildProfileScanQueueFromCandidates22C9J` | QUARANTINE_OR_DELETE | queue entries, target details, target arrays | no by itself | yes | indirect | indirect | queue-builder diagnostics | no | yes, if finalizer treats built DOM queue as canonical success |
| DOM probe fallback finalizer `completeProfileVerifyFromDomProbe22C9J` | QUARANTINE_OR_DELETE | profile scan, verify, classification, harvest queue, layer flags, post-scan snapshot | yes, writes success/verified | yes | yes, writes ready flags | yes, can unlock later actions | yes | yes, invokes reconciliation | yes, strongest legacy overwrite risk |
| Legacy verified scroll scan `runLegacyVerifiedProfileScrollScan22C9ZNOGIT` | QUARANTINE_OR_DELETE | legacy route diagnostics and scan result summary | indirect through caller | indirect through caller | indirect | indirect | yes | no direct reconciliation | yes, can route to DOM finalizer after active failure/no-rounds |
| Backend reconciliation after scan | DIAGNOSTIC_ONLY | queue item collected markers, target details, reconciliation counters | must not create scan success | adjusts new/pending counters | must not override active incompleteness | must not unlock collection alone | yes | yes | yes, if counters are interpreted as scan completeness |
| Readiness active unresolved gate `activeProfilePostScanUnresolved22C14B` | CANONICAL_KEEP | no persisted state | no | no | yes, blocks readiness | yes, keeps Scan Profile | no direct diagnostics | no | prevents bug when active source failed or unresolved |
| Readiness completeness and DOM-only undercount gate `profileScanReady` | CANONICAL_KEEP | no persisted state | no | no | yes | yes | no direct diagnostics | no | prevents bug when DOM-only queue is much smaller than expected |
| Popup active profile-post diagnostic rendering | DIAGNOSTIC_ONLY | no persisted state | no | no | no | no | yes, display only | no | can mask bug only if contradictory fields are displayed as authoritative |
| Legacy state keys and legacy guard | DIAGNOSTIC_ONLY | legacy summary or blocked legacy result | no | no | no | no | yes | no | low; useful for Phase 2 quarantine checks |

## Phase 2 Quarantine Candidates

- Convert DOM probe finalization into a non-authoritative diagnostic path unless active fetch is unavailable for an explicitly small/unknown expected count.
- Add an explicit guard so legacy DOM finalizers cannot write `profile_scan.status=success`, `verify.status=success`, or `layer.profile_scan_ready=true` when active profile-post diagnostics are incomplete or unresolved.
- Keep DOM candidate normalization as a pure helper for tests and diagnostics, but remove its ability to become a production success finalizer for authenticated profile scans.
- Keep backend reconciliation after canonical scan completion, but prevent reconciliation counters from affecting scan completeness decisions.
