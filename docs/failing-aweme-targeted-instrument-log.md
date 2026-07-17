# Failing aweme Targeted Instrumentation Log

Date: 2026-04-29
Scope: minimal evidence-only instrumentation for two failing IDs

Target IDs:
- `7489123456789012346`
- `7489123456789012347`

## Goal
Determine for fields (`posted_*`, `duration_*`, `view/like/comment/share_count`) the first boundary where values disappear:
1) pre-canonical source bundle
2) canonical output
3) backend `_build_item` input/metadata

## Instrumentation Added

### Extension checkpoint 1 (pre-canonical)
- File: `apps/extension-douyin-capture/src/popupTransport.ts`
- Function: `buildDomFallbackMetadata(...)`
- Log marker: `[targeted-aweme-checkpoint1-precanonical]`
- Logs only for the two target aweme IDs.

### Extension checkpoint 2 (canonical output)
- File: `apps/extension-douyin-capture/src/popupTransport.ts`
- Function: `buildCanonicalVideoPayload(...)`
- Log marker: `[targeted-aweme-checkpoint2-canonical]`
- Logs only for the two target aweme IDs.

### API checkpoint 3 (`_build_item`)
- File: `apps/api/src/services/capture_inbox_service.py`
- Function: `_build_item(...)`
- Log marker: `targeted_aweme_checkpoint3_build_item`
- Logs both raw_item input and metadata_json normalized values for only target IDs.

## Evidence Template (fill after run)

### aweme_id=7489123456789012346
- checkpoint1 pre-canonical:
- checkpoint2 canonical:
- checkpoint3 build_item:
- first missing checkpoint per field group:

### aweme_id=7489123456789012347
- checkpoint1 pre-canonical:
- checkpoint2 canonical:
- checkpoint3 build_item:
- first missing checkpoint per field group:
