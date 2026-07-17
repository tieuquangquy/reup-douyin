# Phase 7A CDP Active-Tab Harvest Log

## Scope

Phase 7A replaces primary brittle Douyin modal DOM metric extraction with extension-owned Chrome Debugger Protocol active-tab extraction. The implementation remains local-first and browser-extension-only; it does not add backend crawling, captcha bypassing, automated publishing, or fake metric generation.

## Implemented Sources

1. `cdp_network_aweme`: background service worker attaches to the active supported Douyin tab, enables Network, reads matching response bodies through `Network.getResponseBody`, parses JSON, walks bounded aweme candidates, and caches exact aweme evidence by `aweme_id`.
2. `cdp_runtime_aweme`: background service worker evaluates a bounded runtime scanner in the active tab using `Runtime.evaluate`, looking through selected page/network caches and accessible window state for an exact `aweme_id` match.
3. `page_network_cache_aweme`: existing injected page cache remains available as a high-confidence page cache source.
4. `script_hydration_aweme`: existing hydration scanning remains available below CDP/page-cache priority.
5. `video_element_duration`: retained only as duration fallback.
6. DOM visual fallback: retained only as WARN/emergency/manual fallback evidence.

## Contracts

Probe diagnostics now surface CDP-oriented fields: `aweme_id`, `source_used`, `exact_aweme_found`, `raw_aweme_keys`, metric fields, `confidence_by_field`, `cdp_attached`, response/candidate/exact-match counts, `last_matching_response_url`, and `fallback_used`.

## PASS/WARN/FAIL Behavior

- PASS requires an `aweme_id`, duration, like/comment/favorite/share, and a source of `cdp_network_aweme`, `cdp_runtime_aweme`, or `page_network_cache_aweme`.
- WARN covers exact but incomplete CDP/runtime evidence, legacy runtime/script evidence, and reliable manual fallback cases such as duration plus like with missing comment/favorite/share.
- FAIL covers no aweme id, no duration, no like, or no reliable fallback.

Normal start blocks FAIL. WARN requires the existing explicit `allow_probe_warnings` override path.

## Lifecycle

CDP attach starts on full modal harvest start/resume/probe. CDP stop/detach is best-effort on stop, unload, harvest completion, and harvest errors. Background tests cover attach, enabled domains, detach, and restart cleanup.

## Verification

Focused verification passed with TypeScript, CDP helper tests, modal harvest tests, and background CDP lifecycle tests.