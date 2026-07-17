# Phase 22B-14 Posted dd/mm/yyyy Resume

## Completed
- Added raw/parsed/display posted metadata extraction in [`apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:181).
- Propagated `posted_text_raw`, `posted_display`, `posted_source`, and `posted_parse_confidence` through extension whole-profile harvest types and one-item payload generation in [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:206), [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts:142), and [`apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:558).
- Extended backend ingest schemas in [`apps/api/src/schemas/douyin_extension.py`](apps/api/src/schemas/douyin_extension.py:138) and Capture Inbox response hydration in [`apps/api/src/schemas/capture_inbox.py`](apps/api/src/schemas/capture_inbox.py:114).
- Updated backend persistence in [`apps/api/src/services/douyin_extension_capture_service.py`](apps/api/src/services/douyin_extension_capture_service.py:1151) so `posted_text` becomes display-friendly while `posted_text_raw` preserves the original Chinese source text.
- Added focused extension and backend regression assertions in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) and [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py).
- Added this phase handoff documentation in [`docs/metadata-phase22B-14-posted-dd-mm-yyyy-log.md`](docs/metadata-phase22B-14-posted-dd-mm-yyyy-log.md) and [`docs/metadata-phase22B-14-posted-dd-mm-yyyy-resume.md`](docs/metadata-phase22B-14-posted-dd-mm-yyyy-resume.md).

## Key Findings
- The extension already had enough source information to preserve raw posted text and derive a normalized display date; the missing piece was contract propagation across extension payloads and backend metadata persistence.
- Mapping Capture Inbox response [`posted_text`](apps/api/src/schemas/capture_inbox.py:49) to `posted_display` first satisfies the user requirement without redesigning [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx).
- Raw relative Chinese strings must remain available independently because low-confidence cases should not be forced into synthetic calendar dates.

## Validation Status
- Not yet run: [`npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- Not yet run: [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json:7)
- Not yet run: [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json:6)
- Not yet run: backend unit coverage including [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py)

## Files Touched In This Phase
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts)
- [`apps/extension-douyin-capture/src/types.ts`](apps/extension-douyin-capture/src/types.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`apps/api/src/schemas/douyin_extension.py`](apps/api/src/schemas/douyin_extension.py)
- [`apps/api/src/schemas/capture_inbox.py`](apps/api/src/schemas/capture_inbox.py)
- [`apps/api/src/services/douyin_extension_capture_service.py`](apps/api/src/services/douyin_extension_capture_service.py)
- [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py)
- [`docs/metadata-phase22B-14-posted-dd-mm-yyyy-log.md`](docs/metadata-phase22B-14-posted-dd-mm-yyyy-log.md)
- [`docs/metadata-phase22B-14-posted-dd-mm-yyyy-resume.md`](docs/metadata-phase22B-14-posted-dd-mm-yyyy-resume.md)
