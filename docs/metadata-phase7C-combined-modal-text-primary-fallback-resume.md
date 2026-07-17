# Phase 7C Combined Modal Text Primary Fallback Resume

## Status

Phase 7C implementation is complete in the extension and targeted modal harvest tests pass.

## Files Changed

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `docs/metadata-phase7C-combined-modal-text-primary-fallback-log.md`
- `docs/metadata-phase7C-combined-modal-text-primary-fallback-resume.md`

## Behavior To Preserve

When CDP exact aweme is absent, `combined_modal_text_fallback` must be evaluated before profile-card-like and visible right-rail fallbacks. If the combined text parser finds exactly four action count tokens after `连播`, those values become the authoritative fallback counts for the modal.

Expected live example:

```text
00:00 / 12:56 倍速 智能 清屏 连播 829 16 155 35 听抖音 @地球之旅 · 4月21日 第39集...
```

Expected extraction:

- `like_count = 829`
- `comment_count = 16`
- `favorite_count = 155`
- `share_count = 35`
- `source_used = combined_modal_text_fallback`
- `extraction_mode = combined_modal_text_fallback`
- Probe `PASS` when `duration_seconds` is also present

## Tests Added

- Live combined modal text parses to `829`, `16`, `155`, `35`.
- `连播 6.6万 123 456 78 听抖音` parses to `66000`, `123`, `456`, `78`.
- Timeline text is ignored because parsing starts after `连播`.
- `第39集` and `豆瓣9.8` are ignored when outside the parsed segment.
- Parser returns `null` for fewer or more than exactly four action tokens.
- Combined modal text fallback wins over visible right-rail/profile-card-like values.
- Probe is `PASS` with duration plus four combined action counts.
- Full Modal Harvest uses the same extraction result as Probe.

## Remaining Verification

Run before final handoff:

```cmd
cd apps\\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit
cd apps\\extension-douyin-capture && npx tsx src\\modalHarvest.test.ts
cd apps\\extension-douyin-capture && npm run test
```
