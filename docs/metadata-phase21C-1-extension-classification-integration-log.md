# Phase 21C-1 — Extension Classification Integration Log

## Scope

Phase 21C-1 connects the Douyin extension whole-profile scan flow to the backend `POST /douyin-extension/profile-video-classification` contract after scan candidate discovery. The implementation remains extension-side only and does not rewrite modal extraction, persist collected videos, or add crawler/video processing behavior.

## Implemented behavior

- Added extension-side request and response types for `douyin_profile_video_classification.v1`.
- Added a profile classification request builder that sends scanned candidates with aweme id, video/source URL, thumbnail, caption, posted text, posted date, and view count.
- Added a popup runtime client method that posts to `/douyin-extension/profile-video-classification` via the existing backend message transport.
- Integrated classification after successful profile scan in the whole-profile controller.
- Stored backend classification state in durable whole-profile harvest state.
- Built the collect queue only from backend targets where `collect === true`.
- Preserved backend classifications so `new`, `incomplete`, and `failed` are queued while `complete` and `skipped` are excluded by backend `collect` decisions.
- Updated readiness/action gating so collection requires classification success, a non-empty queue, no security pause, calibration, and dry-run readiness.
- Updated scanner counts to prioritize classification totals/counts after classification succeeds, including the `Need retry` failed count.
- Added/updated tests for profile classification request shape, classification-backed queue behavior, readiness gating, and scanner view-model count mapping.

## Non-goals kept

- No modal extraction rewrite.
- No collected-video save implementation.
- No crawler implementation.
- No old `harvest-plan` endpoint call introduced for main scanner classification.
- No fake local classification for the extension scanner flow.
