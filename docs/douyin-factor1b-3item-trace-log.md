# Douyin Factor 1B 3-Item Identity Trace Log

## Scope

Trace-only diagnostic for the real failing Douyin capture pipeline. No code patch was applied.

Real capture batch used:

- `capture_session_id`: `f6eadbdf-2817-49fa-9d47-cb3a4b576553`
- `capture_id`: `83d80946-7569-4bad-83a9-3cf1a3d3be1c`
- `captured_item_count`: `27`
- Evidence source: local Postgres `captured_items` rows and API response model validation for the same rows.

## Chosen 3 aweme_ids

All three items are from the same real failing capture session and have distinct `aweme_id` values:

| Item | raw_item_index | aweme_id |
|---|---:|---|
| 1 | 0 | `7508570147947334964` |
| 2 | 1 | `7632149506821311763` |
| 3 | 5 | `7629583407210614031` |

## Field shorthand used in tables

The repeated title is abbreviated as:

`置顶8923古人用五音疗愈 “心阳不振”现代人用《精卫》对抗 “精神内耗 ...`

The repeated thumbnail is abbreviated as:

`https://p3-pc-sign.douyinpic.com/tos-cn-i-dy/54a87deae40242dca059d0f7f46e1ede~tplv-dy-cropcenter:323:430.jpeg?...x-signature=SB2AJ%2FiW1Ja5xUsGgjfkfX4SbWM%3D`

## Stage evidence availability

| Stage | Evidence status | Notes |
|---|---|---|
| A. Visible DOM card | Missing direct evidence | No browser DOM snapshot/card HTML was stored for this real capture. The persisted payload only records derived DOM fields and diagnostics. |
| B. Network JSON record | Missing direct record evidence | No network cache artifact for the real capture was stored. The persisted diagnostics show `has_network_metadata=false` for all three chosen items, so no network metadata was attached to these rows. |
| C. Extension normalized item | Missing separate runtime artifact | No independent pre-request extension normalized payload artifact was stored. The closest persisted artifact is Stage D, the submitted request item stored in `raw_payload_json`. |
| D. Extension request payload item | Available | `captured_items.raw_payload_json` contains the exact item submitted by the extension/backend ingest boundary. |
| E. Backend normalized/persisted item | Available | `captured_items` columns show backend-normalized persisted fields. |
| F. API response item | Available by schema projection | `CapturedItemResponse.model_validate(CapturedItem)` reproduces response hydration used by the API route. |
| G. Frontend rendered item | Code-path evidence only, no live screenshot | Frontend uses API fields directly for thumbnail/title/chips; no separate browser-render screenshot was captured for this task. |

## Per-stage trace matrix

### Item 1: aweme_id `7508570147947334964`

| Stage | aweme_id | source_url | thumbnail_url | title | posted_at / posted_text | view_count | like_count | comment_count | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| A DOM card | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | No DOM snapshot/card HTML stored. |
| B Network JSON | No attached network metadata | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | `has_network_metadata=false`; raw network record unavailable. |
| C Extension normalized | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | No pre-request normalized artifact stored. |
| D Extension request payload | `7508570147947334964` | `https://www.douyin.com/video/7508570147947334964` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | `raw_payload_json`; diagnostics: `has_card_root=true`, `card_text_length=4844`, `thumbnail_candidate_count=20`, `has_network_metadata=false`. |
| E Backend persisted | `7508570147947334964` | `https://www.douyin.com/video/7508570147947334964` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | Persisted columns: `source_video_external_id`, `source_url`, `caption`, `thumbnail_url`, `posted_at`. |
| F API response | `7508570147947334964` | `https://www.douyin.com/video/7508570147947334964` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | `CapturedItemResponse` projection sets `aweme_id=source_video_external_id`, `title=caption`, metrics from metadata/raw payload. |
| G Frontend render | `7508570147947334964` displayed via ID line | Source/profile line from API item | repeated thumbnail via resolver | repeated title/caption from API item | `Not captured` | `Not captured` | `Not captured` | `Not captured` | Code-path evidence: tile reads API item fields; no live render screenshot. |

### Item 2: aweme_id `7632149506821311763`

| Stage | aweme_id | source_url | thumbnail_url | title | posted_at / posted_text | view_count | like_count | comment_count | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| A DOM card | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | No DOM snapshot/card HTML stored. |
| B Network JSON | No attached network metadata | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | `has_network_metadata=false`; raw network record unavailable. |
| C Extension normalized | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | No pre-request normalized artifact stored. |
| D Extension request payload | `7632149506821311763` | `https://www.douyin.com/video/7632149506821311763` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | `raw_payload_json`; diagnostics: `has_card_root=true`, `card_text_length=4818`, `thumbnail_candidate_count=20`, `has_network_metadata=false`. |
| E Backend persisted | `7632149506821311763` | `https://www.douyin.com/video/7632149506821311763` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | Persisted columns show same duplicated metadata as Stage D. |
| F API response | `7632149506821311763` | `https://www.douyin.com/video/7632149506821311763` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | API response model preserves Stage E values. |
| G Frontend render | `7632149506821311763` displayed via ID line | Source/profile line from API item | repeated thumbnail via resolver | repeated title/caption from API item | `Not captured` | `Not captured` | `Not captured` | `Not captured` | Code-path evidence: tile reads API item fields; no live render screenshot. |

### Item 3: aweme_id `7629583407210614031`

| Stage | aweme_id | source_url | thumbnail_url | title | posted_at / posted_text | view_count | like_count | comment_count | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| A DOM card | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | No DOM snapshot/card HTML stored. |
| B Network JSON | No attached network metadata | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | Evidence missing | `has_network_metadata=false`; raw network record unavailable. |
| C Extension normalized | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | Evidence missing separately | No pre-request normalized artifact stored. |
| D Extension request payload | `7629583407210614031` | `https://www.douyin.com/video/7629583407210614031` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | `raw_payload_json`; diagnostics: `has_card_root=true`, `card_text_length=4766`, `thumbnail_candidate_count=20`, `has_network_metadata=false`. |
| E Backend persisted | `7629583407210614031` | `https://www.douyin.com/video/7629583407210614031` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | Persisted columns show same duplicated metadata as Stage D. |
| F API response | `7629583407210614031` | `https://www.douyin.com/video/7629583407210614031` | repeated thumbnail | repeated title | `null` / `null` | `null` | `null` | `null` | API response model preserves Stage E values. |
| G Frontend render | `7629583407210614031` displayed via ID line | Source/profile line from API item | repeated thumbnail via resolver | repeated title/caption from API item | `Not captured` | `Not captured` | `Not captured` | `Not captured` | Code-path evidence: tile reads API item fields; no live render screenshot. |

## Cross-item comparison

| Stage | Identity distinct? | Metadata duplicated? | Conclusion |
|---|---|---|---|
| A DOM card | Unknown | Unknown | Direct DOM card evidence missing. |
| B Network JSON | No attached network metadata for these rows | Not applicable | Network merge is not evidenced as the source because `has_network_metadata=false`. |
| C Extension normalized | Unknown separately | Unknown separately | No separate Stage C artifact was stored. |
| D Extension request payload | Yes: three distinct `aweme_id` and `source_video_url` values | Yes: same title and same thumbnail across all three rows | First observed corrupted stage. |
| E Backend persisted | Yes | Yes | Backend persisted the duplicated payload; it did not create new duplicated title/thumbnail values. |
| F API response | Yes | Yes | API response hydration preserves persisted duplication. |
| G Frontend render | Yes by ID line | Yes by title/thumbnail rendering | Frontend renders duplicated API data; no evidence it creates the duplication. |

## First stage where corruption appears

First observed corrupted stage: **Stage D. Extension request payload item**.

The trace does **not** prove Stage A, B, or C are clean because direct evidence is missing for those stages. It does prove that the data is already corrupted before backend normalization/persistence, because `raw_payload_json` already contains distinct `aweme_id` / `source_video_url` values with the same title and thumbnail bundle.

## Suspected root cause at first observed corrupted stage

Because Stage D rows have `has_network_metadata=false`, the duplicated title/thumbnail did not come from a network JSON merge for these three rows. The likely source is DOM-derived extension extraction before request submission:

- `extractVideos()` builds per-link DOM records from `nearestCard()`, `cardText()`, `titleFromCard()`, and `thumbnailFromCard()`.
- The diagnostics show very large card text lengths (`4844`, `4818`, `4766`) and `thumbnail_candidate_count=20` for each chosen item, which is consistent with the selected DOM root being too broad and containing shared/profile-grid-level text/images.
- A too-broad selected card root would make multiple distinct links inherit the same first/highest-scored thumbnail and repeated text bundle.

## Exact file/function likely responsible

Likely responsible area:

- `apps/extension-douyin-capture/src/extractor.ts`
  - `extractVideos()`
  - `nearestCard()`
  - `cardText()`
  - `titleFromCard()`
  - `thumbnailFromCard()`

Also relevant for direct page execution path:

- `apps/extension-douyin-capture/src/popupTransport.ts`
  - in-page `extractVideos()`
  - in-page `nearestCard()`
  - in-page `cardText()`
  - in-page `titleFromCard()`
  - in-page `thumbnailFromCard()`

## Clean/corrupted boundary

| Layer | Status |
|---|---|
| Extension DOM/normalization | Already corrupted by first observed persisted boundary (Stage D); exact earlier point A vs C lacks direct evidence. |
| Extension request payload build | Corrupted. Distinct identities carry duplicated title/thumbnail. |
| Backend normalization/persistence | Preserves corruption; identity remains distinct. |
| API response | Preserves corruption; identity remains distinct. |
| Frontend render | Renders corrupted API data; no evidence frontend creates fan-out. |

## Non-goals honored

- No broad refactor.
- No UI redesign.
- No duration/views/layout changes.
- No thumbnail correctness overhaul.
- No code patch before trace completion.
