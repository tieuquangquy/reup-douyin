# Phase 7A CDP Active-Tab Harvest Operator Guide

## Purpose

Phase 7A makes exact Douyin modal metadata extraction use the active browser tab through Chrome Debugger Protocol first. This reduces dependence on brittle visual modal DOM text and makes the probe tell the operator when extraction is exact, warning-only, or blocked.

## Requirements

- Use Chrome or a Chromium browser that supports extension `debugger` permission.
- Load the rebuilt extension from `apps/extension-douyin-capture`.
- Keep the target Douyin modal open in the active tab.
- Approve the Chrome debugger prompt for the extension when requested.

## Normal Flow

1. Open the desired Douyin profile/video modal in the active tab.
2. Run the current modal probe from the extension UI.
3. Start full modal harvest only when the probe reports PASS.
4. If the probe reports WARN, review the diagnostics and use the explicit warning override only for manual/emergency fallback collection.
5. If the probe reports FAIL, do not start harvest; fix the active tab/modal state first.
6. Stop harvest from the extension UI when needed; CDP detach is best-effort on stop, completion, unload, and errors.

## Probe Result Meaning

- PASS: exact aweme evidence was found through CDP network, CDP runtime, or page network cache, and duration plus like/comment/favorite/share are present.
- WARN: only partial or fallback evidence is available. Examples include duration plus like only, DOM fallback use, or missing comment/favorite/share.
- FAIL: the extension could not identify the current aweme id, duration, like count, or any reliable fallback.

## Diagnostics To Check

- `source_used` and `source_priority_used`: confirm whether CDP network/runtime or page cache was used.
- `exact_aweme_found`: should be true for exact evidence.
- `raw_aweme_keys`: confirms aweme-like object shape without exposing secrets.
- `cdp_attached`: confirms the debugger session attached.
- `cdp_response_count`: confirms network responses were observed.
- `cdp_candidate_aweme_count`: confirms aweme candidates were found in CDP responses.
- `cdp_exact_match_count`: confirms exact candidate cache hits.
- `last_matching_response_url`: helps identify which response supplied the evidence.
- `fallback_used`: indicates whether emergency/manual fallback was involved.

## Safe Retest Steps

1. Rebuild or run tests for the extension.
2. Reload the unpacked extension in Chrome.
3. Open a supported Douyin tab and one modal video.
4. Start probe and verify `cdp_attached` is true after debugger approval.
5. Navigate one or two modal videos so CDP network events can populate.
6. Probe again and expect PASS when exact complete aweme data is present.
7. Start full modal harvest without override only on PASS.
8. Stop harvest and confirm Chrome no longer shows the extension debugging the tab.

## Limitations

Phase 7A does not implement crawling, video processing, scoring, filtering, queue orchestration, database schema, auto-publishing, or captcha bypass behavior.