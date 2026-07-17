# Phase 22C-3B Secret/Debug Leakage Fix Log

## Scope

Phase 22C-3B fixes intermittent Safe Batch Next 10 backend rejection caused by secret/debug-like fields reaching the Capture Inbox item save payload.

## Root cause

The backend recursively rejects payload keys containing secret markers such as `cookie`, `authorization`, `auth_token`, `csrf`, `session`, `password`, `credential`, `local_storage`, `session_storage`, and `browser_profile_path`. The extension-side guard previously used a narrower exact-key deny list, so nested diagnostic/debug objects could pass locally while the backend rejected them.

## Changes

- Added a clean Capture Inbox item DTO builder that constructs the backend payload from explicit whitelisted fields.
- Added a recursive sanitizer for Capture Inbox payload values.
- Added a local secret/debug leakage guard before existing payload validation and backend save.
- Wired one-item backend save to use the clean DTO before backend submission.
- Kept advanced diagnostics in local harvest state only.
- Treated local/backend secret-debug/schema rejection as recoverable in safe batch mode.
- Added per-item batch diagnostics for recent item results, last success, last failure, and current item error.

## Validation notes

- Extension typecheck passed after implementation.
- Focused extension tests were iterated while updating assertions for recoverable safe-batch behavior.
