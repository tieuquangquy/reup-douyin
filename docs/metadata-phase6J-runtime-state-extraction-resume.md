# Phase 6J Runtime State Extraction Resume

## Current Status

Phase 6J runtime-state extraction is implemented in `apps/extension-douyin-capture` and focused verification has passed.

Completed:

- Runtime-first exact aweme extraction in `apps/extension-douyin-capture/src/modalHarvest.ts`.
- Phase 6J source and diagnostic types in `apps/extension-douyin-capture/src/types.ts`.
- Focused runtime extraction tests in `apps/extension-douyin-capture/src/modalHarvest.test.ts`.
- TypeScript compile pass for the extension package.
- Focused modal harvest test pass.

## Key Files

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `docs/metadata-phase6J-runtime-state-extraction-log.md`
- `docs/metadata-phase6J-runtime-state-extraction-operator-guide.md`

## Important Behavior To Preserve

- Exact `aweme_id` match is mandatory before using runtime metadata.
- Runtime state has priority over script hydration, network cache, combined modal text, and visible right-rail fallback.
- Lower-priority fallback fields must not overwrite values already mapped from a higher-priority exact aweme object.
- Raw runtime evidence must remain sanitized and bounded.
- Full Modal Harvest must continue sending exact runtime aweme evidence as `raw_detail_aweme` for backend compatibility.
- Existing visual action-rail extraction remains as fallback only.

## Verification Commands

Focused commands already run successfully:

```cmd
cd apps\\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit
cd apps\\extension-douyin-capture && npx tsx src/modalHarvest.test.ts
```

Final command still expected before closing Phase 6J:

```cmd
cd apps\\extension-douyin-capture && npm run test
```

## Live Retest Focus

Use Probe Current Modal Metrics on a Douyin modal with previously missing visual right-rail metrics. Expected Phase 6J result:

- `source_priority_used` is `exact_aweme_runtime_object`, `exact_aweme_script_hydration_object`, or `exact_aweme_network_cache_object`.
- `exact_aweme_runtime_found` is `true` when runtime/script/cache exact aweme is found.
- `source_used` identifies the concrete source such as `react_fiber_aweme_object`.
- `duration_seconds` and `like_count` are present.
- `probe_status` is `PASS` for exact aweme runtime metadata.
- `fallback_used` is `null` unless an exact object was missing one or more fields.
