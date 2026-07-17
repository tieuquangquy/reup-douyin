# Phase 22C-2C — Posted Date Format Capture Log

## Scope

Implemented Phase 22C-2C only: improve Douyin Posted capture for Chinese relative dates, Chinese absolute dates with and without year, direct publish-time labels, English fallback formats, embedded aweme timestamps, payload diagnostics, and backend lazy normalization.

## Audit Findings

- Canonical parser in `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts` previously handled year-bearing absolute dates and a small Chinese relative subset.
- The active Start Collecting modal fallback in `apps/extension-douyin-capture/src/popup.ts` used a local extractor that did not capture `4月28日` or `@作者 · 4月28日`, so the canonical parser never received those raw strings in real modal flows.
- Capture Inbox response mapping in `apps/api/src/schemas/capture_inbox.py` already hydrated `posted_at`, `posted_text_raw`, `posted_display`, and `posted_text`, but legacy lazy normalization only understood a narrow relative Chinese subset.
- One-item and batch payload creation use the canonical harvest payload builder path, so parser fixes and payload diagnostics remain centralized for current whole-profile collection.

## Implementation

- Added `normalizeDouyinPostedRawText()` to strip leading separators, direct labels, and author prefixes while preserving the original raw text.
- Expanded canonical parsing for:
  - `4月28日`
  - `· 4月28日`
  - `@作者 · 4月28日`
  - `2026年4月28日`
  - `2026年04月28日 06:00`
  - `2026-04-28 06:00`
  - Chinese relative seconds/minutes/hours/days/weeks/months/years
  - English relative fallback strings
  - English absolute fallback strings such as `Apr 28` and `April 28, 2026`
- Added year inference for month/day strings without a year: use reference year unless that date is more than seven days in the future, then use previous year.
- Updated modal fallback extraction in `popup.ts` so aweme-scoped body text can return month/day Posted candidates to the canonical parser.
- Extended embedded script extraction to include `createTimeStr` and Chinese-style absolute date separators.
- Added payload diagnostic metadata fields:
  - `posted_parser_pattern_matched`
  - `posted_reference_time`
  - `posted_timezone`
- Extended backend lazy normalization to parse month/day, absolute Chinese dates, English fallback dates, and month/year relative formats.

## Tests Added

- Extension parser regression assertions in `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`.
- Payload diagnostic assertion for canonical parser pattern coverage.
- Backend Capture Inbox lazy normalization tests in `apps/api/tests/test_capture_inbox_metadata_status.py`.

## Non-goals Preserved

- No Capture Inbox UI redesign.
- No extension UI redesign.
- No batch runner redesign.
- No thumbnail, duration, or metrics logic changes.
- No fake `posted_at` for unparseable low-confidence strings.
- No queue/session clearing or backend save/verify behavior changes.
