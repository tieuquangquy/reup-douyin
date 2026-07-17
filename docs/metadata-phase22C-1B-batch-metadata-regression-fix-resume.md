# Phase 22C-1B Batch Metadata Regression Fix Resume

## Problem
- Next 3 safe batch created Capture Inbox items with regressed metadata:
  - duration could drift
  - posted could show raw Chinese relative text such as `1周前`
- One-item flow already had the correct behavior from earlier phases.

## Root Cause
- Batch did not have a separate active extractor or payload builder.
- `runBatchCollectNext3SafeMode()` already delegated into `runOneItemCollectAndSave()`.
- The real gap was shared parser coverage and missing regression assertions:
  - no `周前` / `星期前` parsing in extension shared posted parser
  - no `周前` / `星期前` lazy normalization in backend Capture Inbox response
  - no explicit tests proving batch payload and verify diagnostics still carried canonical posted and duration fields

## Current Behavior
- Batch still processes at most 3 items.
- Batch still reuses one session.
- Batch still writes checkpoints after each item.
- Each batch item now uses the same canonical one-item metadata pipeline.

## Posted Parser
- Supported week-relative patterns now include:
  - `1周前`
  - `2周前`
  - `一周前`
  - `两周前`
  - `1星期前`
- Raw text is preserved in `posted_text_raw`.
- Parsed display is stored in `posted_display` as `dd/mm/yyyy`.

## Duration Behavior
- Batch payload now carries `selected_duration_source` from the canonical one-item extractor.
- Batch verify diagnostics also capture returned duration fields.

## Backend Mapping
- Capture Inbox item response keeps `posted_text = posted_display` when `posted_display` exists.
- Raw posted text remains available as `posted_text_raw`.

## Validation
- Extension specific test file passed.
- Backend unit tests passed.
- Extension workspace test, typecheck, and build passed.
