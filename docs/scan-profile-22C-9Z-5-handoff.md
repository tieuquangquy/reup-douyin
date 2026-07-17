# 22C-9Z-5 Scan Profile Handoff

## Goal

22C-9Z-5 makes the background-owned Scan Profile route dispatch the legacy verified profile scroll scanner directly after a productive DOM probe. A productive probe must no longer finish as a successful DOM-only scan or silently skip the legacy scan round.

## Runtime Markers

- `SCAN_PROFILE_BACKGROUND_TRACE_VERSION`: `22C-9Z-5`
- `SCAN_PROFILE_BACKGROUND_CONTROLLER_VERSION`: `22C-9Z-5-scan-controller`
- `SCAN_POST_PROBE_HANDOFF_VERSION`: `22C-9Z-5`
- `SCAN_POST_PROBE_HANDOFF_PATCH`: `direct_productive_probe_legacy_dispatch_22C9Z5`

## Required Diagnostics

A productive probe path records:

- `scan_post_probe_productive_gate_result: "productive"`
- `scan_post_probe_before_legacy_dispatch: "yes"`
- `scan_post_probe_after_legacy_dispatch: "yes"`
- `legacy_route_invoked: "yes"`
- `legacy_scanner_route_invoked: "yes"`
- `legacy_scanner_message_type: "DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3"`
- `legacy_scanner_dispatch_source: "direct_productive_probe_handoff_22C9Z5"`
- `scan_engine_used: "legacy_verified_profile_scroll_scanner_22C9Z5"`
- `scan_queue_builder_used: "legacy_verified_target_queue_adapter_22C9Z5"`

## Failure Contract

If the legacy scanner message cannot be delivered, the route finalizes with `legacy_dispatch_failed` and preserves the concrete dispatch reason in `scan_no_round_reason`, for example `legacy_dispatch_failed:legacy_scanner_message_handler_missing`.
