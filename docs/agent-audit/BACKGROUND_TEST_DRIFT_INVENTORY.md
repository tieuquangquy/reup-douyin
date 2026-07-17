# Background Test Drift Inventory

## Phase 1D scope

This inventory documents the `background.test.ts` marker and route drift that currently blocks `npm run typecheck` for the extension package.

No runtime source should change as part of this inventory. Do not change `background.ts`, `contentScript.ts`, controller scanner logic, storage/reset/calibration behavior, action strings, route names, build config, backend, web, or API behavior while using this document.

## Typecheck failure summary

Command run from `apps/extension-douyin-capture`:

```text
npm run typecheck
```

Current result:

```text
src/background.test.ts(17,9): error TS2339: Property '__testDerivePostProbeProductiveGate22C9Z5' does not exist on type 'typeof import(".../src/background")'.
src/background.test.ts(162,42): error TS2820: Type '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I"' is not assignable ... Did you mean '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"'?
src/background.test.ts(221,42): error TS2820: Type '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I"' is not assignable ... Did you mean '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"'?
src/background.test.ts(270,42): error TS2820: Type '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I"' is not assignable ... Did you mean '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"'?
src/background.test.ts(314,42): error TS2820: Type '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I"' is not assignable ... Did you mean '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"'?
src/background.test.ts(341,42): error TS2820: Type '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I"' is not assignable ... Did you mean '"DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"'?
```

## Current protected runtime alignment

Current runtime source confirms the active protected background scan path is 22C11B:

- Accepted background Scan Profile routes: `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` and `DOUYIN_SCANNER_START_SCAN_PROFILE`.
- Canonical content scan message: `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B`.
- Canonical content scan ping: `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING`.
- Runtime authority snapshot probe: `DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B`.
- DOM probe message: `DOUYIN_PROFILE_DOM_PROBE_22C11B`.
- Queue adapter marker: `scan_queue_adapter_22C11B`.
- Active scan engine marker: `minimal_active_works_grid_scanner_22C11B`.
- Terminal successful stop reason: `scroll_converged_queue_accepted_22C11B`.
- Exported productive-gate test helper: `__testDerivePostProbeProductiveGate22C11B`.

The route ownership safety rail already protects these strings.

## Drift inventory

| Location | Failing or stale reference | Category | Current equivalent | Risk classification | Recommended future fix |
|---|---|---|---|---|---|
| `src/background.test.ts:17` | `__testDerivePostProbeProductiveGate22C9Z5` | Removed runtime export / outdated test helper | `__testDerivePostProbeProductiveGate22C11B` | Low runtime risk, high typecheck noise. Runtime has an equivalent helper under the current canonical marker. | Safe to update later by importing `__testDerivePostProbeProductiveGate22C11B` and keeping the same productive/empty/blocked assertions unless behavior has intentionally changed. |
| `src/background.test.ts:58-62` | `DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C12F`, `DOUYIN_SCAN_PROFILE_NETWORK_FIRST_22C12B_PING`, `DOUYIN_SCAN_PROFILE_NETWORK_FIRST_22C12B`, `content_script_version: 22C-12F` | Old route marker / old probe-handoff behavior / outdated test helper fixture | `DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B`, `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING`, `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B`, `22C-11B` diagnostics | Medium test-maintenance risk. These strings do not produce the current type errors directly, but the fixture is incompatible with the current runtime path and would fail once route literals are updated. | Rewrite the scan fixture around the current 22C11B ping, authority snapshot, DOM probe, and minimal scan handler messages. |
| `src/background.test.ts:65-76` | Runtime authority and network-first ping responses for 22C12F / 22C12B | Old probe/handoff behavior | 22C11B authority snapshot and minimal handler self-test | Medium. Represents a previous network-first scanner generation, not the current protected path. | Rewrite against canonical 22C11B behavior, or quarantine as historical network-first tests if future comparison coverage is desired. |
| `src/background.test.ts:77` | `DOUYIN_PROFILE_DOM_PROBE_22C9I` | Old route marker | `DOUYIN_PROFILE_DOM_PROBE_22C11B` | Low runtime risk, medium test-maintenance risk. Current runtime sends the 22C11B DOM probe. | Safe to update later to 22C11B when rewriting the fixture. |
| `src/background.test.ts:94` | `DOUYIN_SCAN_PROFILE_NETWORK_FIRST_22C12B` | Old route marker / old scanner implementation | `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B` | Medium. The expected scanner contract can mostly map to current verified target fields, but diagnostic marker expectations differ. | Rewrite against minimal active works scanner response shape and current diagnostic fields. |
| `src/background.test.ts:106-112` | Productive-gate assertions via old helper name | Outdated test helper | `__testDerivePostProbeProductiveGate22C11B` | Low. Underlying derivation behavior still exists under current name. | Safe to update later with helper rename only after confirming assertion semantics remain valid. |
| `src/background.test.ts:162` | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` | Old action name / route marker | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` or compatibility alias `DOUYIN_SCANNER_START_SCAN_PROFILE` | High typecheck impact, low runtime regression signal. Current runtime intentionally rejects this old literal at type level. | Rewrite this success scenario to use 22C11B route and current content messages; verify queue adapter output under 22C11B markers. |
| `src/background.test.ts:167-172` | Assertions expecting 22C12F authority snapshot, 22C12B ping/scan, `live_network_stream_profile_collector_22C12F`, `network_stream_queue_adapter_22C12D` | Old route marker / old probe-handoff behavior | `DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B`, `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING`, `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B`, `minimal_active_works_grid_scanner_22C11B`, `scan_queue_adapter_22C11B` | Medium. These would be runtime assertion failures after type-only fixes. | Rewrite expected sent messages and diagnostics to current canonical names. |
| `src/background.test.ts:221` | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` | Old action name / route marker | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` or `DOUYIN_SCANNER_START_SCAN_PROFILE` | High typecheck impact. Also this block expects incomplete-under-count behavior that current 22C11B finalizer no longer enforces the same way. | Rewrite against current finalizer semantics, or quarantine as historical expected-count strictness coverage before deciding whether behavior should return. |
| `src/background.test.ts:226-233` | Expects network-first scan message and incomplete state for 33 of expected 45 | Old probe/handoff behavior / expected behavior changed | Current finalizer accepts any non-empty canonical queue as ready and records count diagnostics rather than failing under-count | Medium-to-high product semantics risk to review manually. This is not a typecheck-only rename. | Dedicated fix phase should decide whether the current permissive finalizer is desired. If desired, update test to assert diagnostics only. If not desired, open a separate runtime behavior task before changing code. |
| `src/background.test.ts:270` | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` | Old action name / route marker | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` or `DOUYIN_SCANNER_START_SCAN_PROFILE` | High typecheck impact. | Rewrite route and fixture to 22C11B. |
| `src/background.test.ts:275-278` | Expects `success_unknown_expected`, `fresh_network_post_only`, ready=true | Old result label / stale diagnostic expectation | Current terminal result is `success`; `queue_source_mode` remains `fresh_network_post_only`; ready=true for non-empty queue | Low-to-medium. Mostly assertion label drift. | Safe to update later after canonical 22C11B fixture rewrite. |
| `src/background.test.ts:314` | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` | Old action name / route marker | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` or `DOUYIN_SCANNER_START_SCAN_PROFILE` | High typecheck impact. | Rewrite route and fixture to 22C11B. |
| `src/background.test.ts:319-321` | Expects `overcollected` failure when queue exceeds expected count | Old expected behavior / stale count reconciliation assertion | Current 22C11B terminal reconciliation accepts any non-empty queue as ready; overcollection is diagnostic-only in current code path | Medium-to-high product semantics risk to review manually. Not evidence of runtime regression by itself. | Quarantine or rewrite after deciding whether strict expected-count enforcement remains a product requirement. Do not change runtime in the test-drift phase. |
| `src/background.test.ts:341` | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` | Old action name / route marker | `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` or `DOUYIN_SCANNER_START_SCAN_PROFILE` | High typecheck impact. | Rewrite route and fixture to 22C11B. |
| `src/background.test.ts:346-348` | Expects malformed/null scanner response to produce `canonical_scanner_completed_without_result` and no queue adapter invocation | Expected behavior still exists under current canonical path | Current `runScanProfile22C11B` still fails malformed/missing scanner responses with `canonical_scanner_completed_without_result` and `canonical_queue_adapter_invoked: no` | Low. Behavior appears current and safe to preserve. | Safe to update later with current route/handler names while preserving the failure assertions. |
| `src/background.test.ts:495` | Console label says 22C-12F | Old marker label | 22C-11B / current canonical background scan route | Low. Cosmetic test output drift. | Update after the dedicated drift-fix phase rewrites the scan blocks. |

## Runtime regression assessment

The observed typecheck failures do not indicate a confirmed runtime regression.

Current runtime source accepts the protected canonical Scan Profile routes and dispatches the protected canonical content scanner. The missing helper export has a current equivalent under the 22C11B marker. The old `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` action string is absent from the current typed message union by design.

However, the stale `background.test.ts` scan blocks also contain behavioral expectations from the previous network-first generation. In particular, strict under-count and over-count failures should be reviewed in a dedicated fix phase because current 22C11B finalization accepts any non-empty canonical queue and records count diagnostics. That is a test/runtime expectation mismatch, not a Phase 1D runtime change request.

## Recommended future fix strategy

1. Keep this Phase 1D inventory docs-only.
2. In a dedicated test-drift fix phase, edit `apps/extension-douyin-capture/src/background.test.ts` only unless a separate product decision requires runtime changes.
3. Rename the productive-gate helper import from `__testDerivePostProbeProductiveGate22C9Z5` to `__testDerivePostProbeProductiveGate22C11B`.
4. Rewrite `installChromeForScanTest` so supported handlers and `sendMessage` branches model current 22C11B route ownership:
   - `DOUYIN_SCANNER_PING`
   - `DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B`
   - `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING`
   - `DOUYIN_PROFILE_DOM_PROBE_22C11B`
   - `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B`
5. Replace `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I` with `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` in active canonical scan tests.
6. Update diagnostic expectations from network-first 22C12F/22C12D names to current 22C11B names.
7. Split behavior-sensitive count reconciliation cases:
   - Preserve current behavior tests if current accepted-queue finalization is intended.
   - Quarantine or separately redesign strict under-count/over-count tests if product wants that behavior back.
8. Keep CDP lifecycle and backend post tests unchanged unless the rewrite discovers unrelated failures.

## Files likely to edit in future fix phase

- `apps/extension-douyin-capture/src/background.test.ts`
- `docs/agent-audit/EXTENSION_CLEANUP_PLAN.md`
- Optionally this inventory document, if the fix phase records final disposition.

Runtime files should not be edited in the future test-drift fix phase unless a separate approved runtime behavior task is created.

## Exact checks to run after future fix

From `apps/extension-douyin-capture`:

```text
npm run typecheck
npx tsx src/background.test.ts
npx tsx src/routeOwnership.test.ts
npx tsx src/extensionReset.test.ts
npx tsx src/phase18aPopupCleanup.test.ts
npm run build
```

## Phase 2A disposition

Changed files:

- `apps/extension-douyin-capture/src/background.test.ts`
- `docs/agent-audit/BACKGROUND_TEST_DRIFT_INVENTORY.md`
- `docs/agent-audit/EXTENSION_CLEANUP_PLAN.md`

What changed:

- `background.test.ts` now imports the current helper `__testDerivePostProbeProductiveGate22C11B` instead of the removed `__testDerivePostProbeProductiveGate22C9Z5` helper.
- Active Scan Profile messages now use `DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B` with `22C-11B` trace metadata.
- The scan fixture now models current 22C11B route ownership:
  - `DOUYIN_SCANNER_PING`
  - `DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B`
  - `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING`
  - `DOUYIN_PROFILE_DOM_PROBE_22C11B`
  - `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B`
- Stale diagnostic expectations were aligned from `live_network_stream_profile_collector_22C12F` and `network_stream_queue_adapter_22C12D` to `minimal_active_works_grid_scanner_22C11B` and `scan_queue_adapter_22C11B`.

What was rewritten:

- Under-count and over-count tests no longer expect terminal failure solely because the discovered queue count differs from the expected profile video count.
- Those tests now assert current 22C11B finalizer behavior: non-empty canonical queues finish with `lastScannerResult: success`, `lastScannerError: none`, `profile_scan_ready: true`, and `scanStop: scroll_converged_queue_accepted_22C11B`.
- Count mismatch coverage remains as diagnostics by asserting fields such as `expected_profile_video_count`, `profile_queue_total_count`, `missing_profile_video_count`, `over_collected_count`, `count_delta`, and `profile_scan_completion_ratio`.
- Malformed/null scanner response coverage was preserved and still asserts `canonical_scanner_completed_without_result` with `canonical_queue_adapter_invoked: no`.

Strict count behavior decision:

- Phase 2A keeps current runtime behavior. Under-count and over-count are diagnostic conditions for non-empty canonical queues, not terminal runtime failures.
- No compatibility route was added for `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I`.
- No runtime marker was renamed.
- No runtime behavior changed.

Checks run:

- `npx tsx src/background.test.ts` passed.
- `npm run typecheck` passed.
- `npx tsx src/routeOwnership.test.ts` passed.
- `npx tsx src/extensionReset.test.ts` passed.
- `npx tsx src/phase18aPopupCleanup.test.ts` passed.
- `npm run build` passed.

## Explicit non-goal

This inventory does not rename runtime markers, does not add compatibility for `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I`, and does not change scanner, route, storage, reset, calibration, backend, web, API, or build behavior.
