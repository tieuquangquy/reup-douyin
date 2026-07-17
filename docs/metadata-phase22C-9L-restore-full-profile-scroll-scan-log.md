# Phase 22C-9L Restore Full Profile Scroll Scan Log

## Audit
- Old working functions: `scanModalWholeProfileCardsInPage(...)` delegates to `collectProfileCardsUntilStable(...)` in `apps/extension-douyin-capture/src/modalWholeProfileTest.ts`.
- Old scroll loop: wait for profile grid preflight, select scroll container, extract cards every round, scroll by about 75% viewport, wait for lazy loading, bounce at bottom, and continue until a stop condition is met.
- Old stop conditions: `expected_count_reached`, `stable_no_new_ids`, `reached_bottom`, `max_rounds`, `max_total_time`, `scroll_failed`, and no-card/preflight failures.
- Old selectors: video links, modal/aweme links, aweme/data attributes, post/work/card/video containers, and bounded card-context regex extraction.
- Old queue entry shape: scanner cards normalize to target details, classification returns canonical harvest queue items with source URL, target URL, status, capture status, retry counters, and profile URL.
- Old expected count source: `detectExpectedProfileVideoCount()` from profile tab text, reported as `expected_count_source: profile_tab_text` or `unavailable`.
- Old diagnostics: per-round counts, selector attempts, scroll container diagnostics, expected/missing counts, final aweme IDs, candidate classifications, source counts, preflight status, and partial scan flags.
- DOM Probe queue builder change: `completeProfileVerifyFromDomProbe22C9J(...)` could build and finalize a queue directly from DOM Probe candidates with `stop_reason: dom_probe_queue_built`, which truncated Scan Profile to probe samples.

## Implementation
- Added `runFullProfileScrollScan22C9L(...)` contract in the controller to make DOM Probe a preflight input and route normal success through the full scroll scanner.
- Kept DOM Probe queue construction only as an explicit emergency fallback with `scan_fallback_used: dom_probe_queue_fallback`.
- Stamped active scanner/controller versions as 22C-9L.
- Added diagnostics for full scroll scanner contract, round summaries, scroll diagnostics, full queue source, and batch-limit semantics.
