# Phase 6I Modal Action Rail + Progress Resume

## Current target

Make Full Modal Harvest production-ready before the full 51-video run by improving modal action rail extraction, adding a probe/self-check path, and exposing progress/ETA clearly.

## Root cause summary

- Current modal extraction can work for one item, but it still misses `comment_count` on real Douyin profiles.
- The extractor needs a stronger action-rail model with vertical-order fallback.
- Operators also need a probe step and clearer progress before committing to a long-running full harvest.

## Intended post-fix behavior

- like/comment/favorite/share come from a structured action rail extractor
- semantic classification wins when present
- vertical order fallback handles obfuscated icon/class cases
- probe runs before full harvest start
- start blocks when the modal is not harvest-ready
- progress includes ETA and recent extracted items

## Verification plan

- extension typecheck
- extension test suite with new action rail / probe / progress assertions
- no backend changes unless payload shape needs narrow alignment

## Result

- implemented and verified
- semantic action-block classification stays primary
- vertical-order fallback now applies only to unclassified action blocks
- candidate blocks are limited to the visible right-side rail geometry
- probe output can be reviewed before a long harvest run
- harvest progress now exposes ETA and recent-item summaries
