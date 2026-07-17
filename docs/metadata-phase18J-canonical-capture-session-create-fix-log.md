# Phase 18J Canonical Capture Session Create Fix Log

## Scope

Phase 18J fixes canonical Whole Profile Harvest failing before target processing with `capture_session_create_failed` by aligning the extension capture session request with the API endpoint and adding hard diagnostics.

## Root Cause

The extension canonical request used `source: "whole_profile_harvest"` and `mode: "whole_profile_harvest"`, but the API `DouyinExtensionCaptureSessionRequest` schema only accepted `whole_profile_staged_harvest_v2`. The API therefore rejected canonical session creation with HTTP 422, while the extension collapsed that failure into generic `capture_session_create_failed`.

## Changes

- API capture session schema now accepts both `whole_profile_harvest` and `whole_profile_staged_harvest_v2`.
- API response now includes `ok: true` and `run_id`.
- API session creation idempotency is source-aware by `capture_id = "{source}:{run_id}"`.
- Canonical session creation still creates zero video items.
- Extension session creation now persists `debug.last_request_summary` before the backend request.
- Extension session creation now persists `debug.last_response_summary` for success and failure responses.
- Extension session failures classify 404, 422, 500, network, and missing session id separately.
- Extension stops before opening target modals or flushing payloads when session creation fails.
- Progress summary displays capture session status and failure diagnostics.

## Non-Goals

- No profile scanner changes.
- No dry-run changes.
- No V2 runtime migration.
- No fake item creation.
- No `/douyin-extension/full-modal-harvest` call before a capture session exists.
