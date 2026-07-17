# Phase 17B Modal Data Integrity Resume

## Current State

Phase 17B modal data integrity hardening has been implemented for the extension and API paths used by full-modal Douyin harvest.

## Important Files

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/scripts/audit_douyin_duplicate_modal_metrics.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`

## Behavior To Preserve

- The queue target aweme id is the source of truth for extraction and commit.
- A modal metrics payload is valid only when target, modal-before, modal-after, extracted, payload, source video, and raw metric ids agree.
- A mismatch must fail the target with `data_integrity_mismatch` and must not enqueue, flush, or mark updated.
- Backend updates only exact Douyin `source_video_external_id` matches.
- Unmatched rows can only be created under finalized-only policy when full metadata is present and identity is clean.

## Commands Already Run

- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`: passed.
- `python -m compileall apps\\api\\src apps\\api\\scripts\\audit_douyin_duplicate_modal_metrics.py`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build`: passed.

## Notes

One initial API unittest invocation from the repository root failed because `src` was not on `PYTHONPATH`; rerunning from `apps/api` passed.
