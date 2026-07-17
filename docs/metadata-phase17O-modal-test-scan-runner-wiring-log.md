# Phase 17O Modal Test Scan Runner Wiring Log

## Scope

Phase 17O is limited to `apps/extension-douyin-capture` plus tests and documentation for Modal Whole Profile Test scanner wiring.

## Problem

The Modal Whole Profile Test could reach `scanning_profile` with same-context profile readiness diagnostics, but fail with `profile_scan_runner_not_started` while retaining running scan statuses and producing no scan rounds or selector attempts.

## Root Cause

The popup marked the scanner as running before proving that a scanner handler was registered and before the scanner invocation had started. The scan path relied on direct script execution without a standardized content-script scan message, so handler registration and message-send diagnostics were unavailable when startup failed.

## Changes

- Added `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE_PING` and `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE` to the extension message contract.
- Registered content-script handlers for ping and async profile scan execution.
- Added popup ping-before-scan flow with one reconnect/inject attempt and precise handler diagnostics.
- Added `starting` scan lifecycle status before the runner starts, then `running` only after invocation starts.
- Added `scanner_invocation_mode` tracking for `content_script_message` and `direct_same_context`.
- Added first-round `round_started` scanner progress callback.
- Normalized failed scan states so scan statuses do not remain `running` after failure.

## Non-Goals

- No backend changes.
- No Tile Gallery changes.
- No modal metric extraction changes.
- No calibration changes.
- No CDP/debug workflow reintroduction.
- No full-modal-harvest call in verify-only mode.
