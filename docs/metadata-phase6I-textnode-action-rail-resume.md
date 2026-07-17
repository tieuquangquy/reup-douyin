# Phase 6I-F Text-Node Action Rail Extraction Resume

## Completed

- Read `AGENTS.md` and kept the change scoped to Phase 6I-F.
- Updated `apps/extension-douyin-capture/src/types.ts` with text-node action rail diagnostics.
- Updated `apps/extension-douyin-capture/src/modalHarvest.ts` so compact action rail counts are extracted from rendered text-node geometry with `TreeWalker` and `Range.getBoundingClientRect()`.
- Removed the active broad ancestor caption/card rejection path that produced `ancestor_caption_or_card_text_detected` for valid compact counts inside noisy Douyin modal containers.
- Preserved actual profile/video anchor rejection through `a[href*="/video/"]` ancestry checks.
- Preserved active video/modal geometry and x-cluster action rail selection.
- Added selected cluster diagnostics, including selected texts and text-node rects.
- Updated `apps/extension-douyin-capture/src/modalHarvest.test.ts` with fake text-node traversal/range geometry and Phase 6I-F coverage.
- Ran focused modal harvest tests successfully before documentation.

## Current Behavior

Action rail extraction now:
- selects the active video/modal geometry first
- walks rendered text nodes in the document
- normalizes each text node to compact text
- keeps compact count-like text such as `161`, `94`, `623`, `109`, `6.6万`, `8.0万`
- measures each candidate with `Range.getBoundingClientRect()`
- rejects candidates only with text-node-specific geometry/source rules
- clusters eligible compact text-node candidates by x-position and vertical stacking
- maps the selected cluster by y order to like, comment, favorite, share
- exposes diagnostics for candidate count, selected cluster, selected texts, selected rects, assigned metrics, probe status, and warning reason

## Tests Run So Far

```cmd
cd apps\extension-douyin-capture && npx tsx src/modalHarvest.test.ts
```

Result: passed.

## Pending Verification

Run TypeScript compile after docs/test edits:

```cmd
cd apps\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit
```

Run full extension tests:

```cmd
cd apps\extension-douyin-capture && npm run test
```

## Live Retest Steps

1. Build or reload the unpacked Chrome extension from `apps/extension-douyin-capture`.
2. Open the Douyin full modal where the live issue was observed.
3. Confirm the modal video is active and duration is visible/playable.
4. Open the extension popup.
5. Run Probe Current Modal Metrics.
6. Confirm diagnostics show:
   - `active_video_rect`
   - `compact_text_node_candidates_count`
   - `selected_compact_count_cluster`
   - `selected_cluster_texts`
   - `selected_cluster_rects`
   - no valid compact count rejected as `ancestor_caption_or_card_text_detected`
7. Confirm metric assignment:
   - first selected cluster text by y order = like
   - second = comment
   - third = favorite
   - fourth = share
8. Confirm status behavior:
   - all four counts plus duration = `PASS`
   - duration plus like only = `WARN` with override required
   - no reliable compact count cluster = `FAIL`

## Final Report Checklist

The final Phase 6I-F report must include exactly:
1. root cause
2. files/functions changed
3. text-node geometry extraction method
4. cluster selection method
5. PASS/WARN/FAIL behavior
6. tests run
7. verification result
8. live retest steps
