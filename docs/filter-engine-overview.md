# Filter Engine Overview

The filter engine selects source videos that are worth sending to the review board. It is separate from scoring: filters decide whether a video is eligible, while Reup Score ranks and explains eligible videos.

## Input Data

The engine works on normalized `SourceVideo` data plus the latest `VideoMetricSnapshot`, open `RiskFlag` records, and optional content signals stored in `source_videos.metadata_json`.

Currently reliable from ingest:

- posted date when present
- duration when present
- views, likes, comments, shares, favorites
- hashtags and thumbnail URL in metadata

Expected to improve after later analysis steps:

- speech/no-speech
- text density
- live replay/slideshow flags
- heavy watermark signal
- processing complexity
- copyright risk

Missing signals are handled gracefully and surfaced as warnings.

## Filter Config

Filters support:

- date mode: `absolute_range`, `last_n_days`, `latest_n_videos`
- metric thresholds
- duration thresholds
- engagement ratio thresholds
- speech and text density conditions
- exclusion flags for live replay, slideshow, watermark, copyright risk, and processing complexity
- sort: `score_desc`, `newest_first`, `views_desc`, `engagement_desc`
- pagination

## Preview Vs Apply

`POST /candidates/filter/preview` evaluates filters and score without writing `VideoCandidate`.

`POST /candidates/filter/apply` evaluates filters and upserts the latest `VideoCandidate` row for matched videos. Phase 1 stores the latest evaluation per source video, not a full historical evaluation session table.

## Persistence Strategy

`video_candidates` stores:

- selected preset name
- serialized filter config
- score version
- total score and score label
- score breakdown JSON
- inclusion and exclusion reasons
- warnings
- evaluated timestamp

This is enough for the next review board step while keeping schema weight low.

## Current Limits

- No advanced historical growth ranking yet.
- No UI.
- No download or media analysis.
- Content-signal filters become more accurate after OCR/STT/watermark analysis exists.

