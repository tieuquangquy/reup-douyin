# Phase 6I-G Icon-Anchored Action Rail Log

## Scope

Phase 6I-G changes only the Douyin extension modal metric extractor. The goal is to stop assigning modal engagement metrics from compact numeric clusters alone and instead anchor every extracted count to a visible right-rail action icon.

## Root Cause

The previous Phase 6I-F text-node geometry detector correctly measured rendered numeric text, but the final metric mapping still trusted compact number clusters. On live Douyin modal pages, caption, chapter, rating, and player-control text can form compact numeric groups such as `5`, `3`, and `0`. Because those groups were not required to have matching action icons above them, the extractor could map distracting text to like/comment/favorite/share.

## Implementation

- Added icon candidate diagnostics and icon-anchored per-metric diagnostics to extension shared types.
- Updated modal action extraction to collect visible icon/button candidates first.
- Aggregated icon semantic hints from aria labels, titles, hrefs, classes, SVG title descendants, SVG use hrefs, parent hints, and nearby text.
- Identified semantic icon kinds for like, comment, favorite, and share.
- Added visual-order fallback only after selecting icon-like right-rail candidates.
- For every selected icon, selected the closest compact numeric text below it in the same x-band.
- Preserved Probe Current Modal Metrics and Full Modal Harvest on the same shared extraction path.
- Added diagnostics for icon candidates, selected action icons, icon-anchored metrics, rejected number examples, and rejected icon examples.

## Exclusions

Count candidates are rejected when they are inside profile grid video anchors, search boxes, left caption/content areas, bottom player controls, or when their text/nearby context contains hard-excluded content such as `章节要点`, `豆瓣`, `纪录片`, `#`, `关注`, `合集`, `播放进度`, or current/total time patterns.

## Tests

- `cd apps\\extension-douyin-capture && npx tsc -p tsconfig.json --noEmit`
- `cd apps\\extension-douyin-capture && npx tsx src/modalHarvest.test.ts`
- `cd apps\\extension-douyin-capture && npm run test`

All commands passed.

## Verification Fixture

The focused fixture uses visible icon/count pairs:

- heart icon + `419`
- comment icon + `17`
- favorite/star icon + `80`
- share icon + `33`

Distractors include chapter text, `5`, `3`, `0`, `豆瓣9.8`, bottom player time text, and profile-grid numbers. Expected extracted values are exactly `419`, `17`, `80`, and `33`.
