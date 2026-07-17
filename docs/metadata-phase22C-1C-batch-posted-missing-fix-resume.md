# Phase 22C-1C Batch Posted Missing Fix Resume

## Problem
- Batch Next 3 saved and verified items correctly.
- Capture Inbox still showed `Posted: Not captured` for batch-created items.

## Root Cause
- Batch was not bypassing backend or payload mapping.
- The actual problem was earlier in the extension producer:
  - `popup.ts -> extractModalMetrics()` parsed Posted evidence
  - but failed to pass canonical Posted fields into the one-item payload builder

## Current Behavior
- Batch still runs through:
  - `runBatchCollectNext3SafeMode()`
  - `runOneItemCollectAndSave()`
  - `buildCaptureInboxItemPayload()`
  - backend save
  - backend verify
- Each batch item now carries full Posted metadata when evidence exists.

## Diagnostics
- Per item:
  - payload Posted fields
  - verified backend Posted fields
  - `posted_lost_in_backend`
- Per batch:
  - extracted/missing/verified/lost Posted counters

## Frontend Impact
- Capture Inbox frontend files were not modified.
- Fix is delivered via extension producer data and backend response mapping already in place.

## Validation
- Focused whole-profile harvest test passed.
- Full extension workspace test/typecheck/build passed.
- Backend targeted tests and compileall passed.
