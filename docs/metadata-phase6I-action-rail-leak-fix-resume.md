# Phase 6I-C Action Rail Leak Fix Resume

## Goal

Stop Full Modal Harvest from leaking background profile grid numbers into modal `comment_count`, `favorite_count`, and `share_count`.

## Expected result

- modal rail counts come only from compact right-side rail units
- background card text like `872 ... 豆瓣9.7 ...` is rejected
- probe shows accepted blocks and rejected candidate examples before a full run

## Verification

- extension typecheck
- extension test suite with exact 2695/94/623/109 mapping
- no backend changes required
