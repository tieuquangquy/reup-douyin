# Douyin Factor 1B 3-Item Identity Trace Resume

## Task status

Trace-only diagnostic completed. No code changes were made.

## Chosen 3 aweme_ids

Same real failing capture session:

- `capture_session_id`: `f6eadbdf-2817-49fa-9d47-cb3a4b576553`
- `capture_id`: `83d80946-7569-4bad-83a9-3cf1a3d3be1c`

Chosen items:

1. `7508570147947334964` (`raw_item_index=0`)
2. `7632149506821311763` (`raw_item_index=1`)
3. `7629583407210614031` (`raw_item_index=5`)

## Trace result summary

First observed corrupted stage: **Stage D. Extension request payload item**.

Evidence:

- Stage D `raw_payload_json` already has three distinct `aweme_id` values.
- Stage D `raw_payload_json` already has three distinct `source_video_url` values.
- Stage D `raw_payload_json` already repeats the same title and same thumbnail for all three items.
- Stage D diagnostics show `has_network_metadata=false` for all three items.
- Stage D diagnostics show `has_card_root=true`, card text lengths around `4766` to `4844`, and `thumbnail_candidate_count=20`, indicating DOM-card-derived extraction from a likely broad root.
- Stage E persisted columns preserve the same duplicated title/thumbnail.
- Stage F `CapturedItemResponse` hydration preserves the same duplicated title/thumbnail.
- Stage G frontend code renders the API item values directly for title, caption, thumbnail, IDs, and metadata chips.

## Missing stage evidence

The trace must not claim unsupported evidence for these stages:

- Stage A Visible DOM card: direct DOM/card HTML evidence is missing.
- Stage B Network JSON record: direct network JSON record/cache artifact is missing. For the chosen rows, persisted diagnostics indicate no network metadata was attached.
- Stage C Extension normalized item: no separate pre-request normalized runtime artifact exists; Stage D `raw_payload_json` is the earliest stored boundary artifact.
- Stage G Frontend rendered item: no live browser screenshot/DOM render evidence was captured; only code-path evidence is available.

## Likely responsible file/functions

Primary likely file/function area:

- `apps/extension-douyin-capture/src/extractor.ts`
  - `extractVideos()`
  - `nearestCard()`
  - `cardText()`
  - `titleFromCard()`
  - `thumbnailFromCard()`

Direct page execution duplicate implementation also likely relevant:

- `apps/extension-douyin-capture/src/popupTransport.ts`
  - in-page `extractVideos()`
  - in-page `nearestCard()`
  - in-page `cardText()`
  - in-page `titleFromCard()`
  - in-page `thumbnailFromCard()`

## Layer classification

| Layer | Classification |
|---|---|
| Extension normalization / request payload | Corrupted by first observed stored boundary. |
| Backend normalization/persistence | Preserves already-corrupted payload. |
| API response | Preserves already-corrupted persisted data. |
| Frontend render | Renders already-corrupted API data. |

## Next narrow fix target

Target only the extension DOM-card extraction boundary:

1. Add a narrowly scoped failing test that simulates multiple distinct video links under a shared container where the current `nearestCard()` / `thumbnailFromCard()` can select the same broad root.
2. Tighten card-root selection so each link resolves to an item-local card, not a profile/grid/shared ancestor.
3. Keep request payload identity behavior unchanged: distinct `aweme_id` remains canonical.
4. Keep backend/API/frontend untouched unless a new trace proves corruption starts there.

## Stop condition

Stop after documenting the trace and proposed next narrow fix. Do not patch code as part of Factor 1B trace-only work.
