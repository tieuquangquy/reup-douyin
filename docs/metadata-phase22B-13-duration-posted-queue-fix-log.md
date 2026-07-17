# Phase 22B-13 Duration/Posted Queue Fix Log

## Scope
- Implement Phase 22B-13 only within the existing one-item Start Collecting flow.
- Fix duration extraction so saved duration comes from aweme-scoped exact metadata instead of loose modal fallbacks.
- Fix posted extraction so aweme `create_time` is preserved as posted metadata and caption text is not misused as posted text.
- Fix one-item queue selection/pending accounting so each click advances through the preserved queue and only reports no-pending when the queue is truly exhausted.
- Do not redesign popup UI, Capture Inbox UI, or batch workflow behavior.

## Changes Applied
- [`mapRuntimeAwemeMetrics()`](apps/extension-douyin-capture/src/modalHarvest.ts:2525) now records aweme-scoped duration diagnostics, stops mapping [`aweme.desc`](apps/extension-douyin-capture/src/cdpAweme.ts:1) into posted text, and emits [`posted_at`](apps/extension-douyin-capture/src/modalHarvest.ts:2572)-backed metadata from aweme `create_time`.
- [`extractCurrentModalMetricsForAweme()`](apps/extension-douyin-capture/src/modalHarvest.ts:1694) now accepts exact-aweme duration only as saved duration truth, keeps video/timeline values as diagnostics-only candidates, and records [`duration_validation_result`](apps/extension-douyin-capture/src/modalHarvest.ts:1968), [`duration_candidate_list`](apps/extension-douyin-capture/src/modalHarvest.ts:1969), [`posted_source`](apps/extension-douyin-capture/src/modalHarvest.ts:2038), and [`posted_parse_confidence`](apps/extension-douyin-capture/src/modalHarvest.ts:2039).
- [`mapCdpAwemeMetrics()`](apps/extension-douyin-capture/src/cdpAweme.ts:77) now mirrors the aweme-scoped duration diagnostics and preserves only [`posted_at`](apps/extension-douyin-capture/src/cdpAweme.ts:120) from aweme `create_time`.
- [`WholeProfileHarvestMetrics`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:206) now carries duration diagnostics and posted provenance fields through the whole-profile flow.
- [`buildRawEvidenceSummaryForCanonicalHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:333) and [`buildCaptureInboxItemPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:401) now propagate duration diagnostics, prefer extracted aweme-scoped posted metadata over profile-card fallback when present, preserve posted provenance, and treat [`posted_at`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:418) as sufficient metadata for ready status.
- [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2884) now selects the next target through [`getFirstPendingTargetForOneItemCollect()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:370), preserving prior completed targets in queue traversal.
- [`checkpointLocalHarvestTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3890) now counts both `pending` and `processing` items when computing remaining queue state so one-item continuation does not prematurely exhaust the queue.

## Regression Coverage Added
- [`apps/extension-douyin-capture/src/cdpAweme.test.ts`](apps/extension-douyin-capture/src/cdpAweme.test.ts) now asserts duration diagnostics and confirms [`posted_text`](apps/extension-douyin-capture/src/cdpAweme.test.ts:82) is no longer sourced from caption text.
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) now asserts extracted posted metadata precedence, aweme-scoped [`posted_at`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1086) propagation, [`posted_at`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1124)-only readiness, and preserved posted provenance in raw modal metrics.

## Validation Notes
- [`npx tsx apps/extension-douyin-capture/src/cdpAweme.test.ts`](apps/extension-douyin-capture/src/cdpAweme.test.ts) passed.
- [`npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) passed.
- [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json:7) passed.
- Workspace-level [`npm test`](package.json:20) still fails for pre-existing unrelated API classification issues in [`apps/api/tests/test_douyin_profile_video_classification.py`](apps/api/tests/test_douyin_profile_video_classification.py).
