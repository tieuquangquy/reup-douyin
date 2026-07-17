# Intake Filters Spec

## Presets

| Preset | Title | Definition | Operator guidance | Backend support |
| --- | --- | --- | --- | --- |
| none | No preset | Uses only manually entered filters. | Use when testing exact thresholds. | Supported by sending `preset_name=null`. |
| viral_discovery | Viral Discovery | Recent, high-engagement, likely viral candidates. | Good first pass after profile ingest; custom filters refine thresholds. | Supported by backend preset registry. |
| safe_reup | Safe Reup | Lower-risk, easier-to-process candidates. | Use when operator wants fewer editing/risk surprises. | Supported by backend preset registry. |
| affiliate_priority | Affiliate Priority | Medium-length, easy-to-localize, conversion-friendly candidates. | Use for product or affiliate review queues. | Supported by backend preset registry. |

Custom filters submitted from `/intake` override or refine preset thresholds. When the operator explicitly sets speech to yes/no, intake maps that choice onto the existing speech-required/no-speech guardrails so preset defaults do not contradict the chosen value.

## Filter Fields

| Field | Type | Validation | Backend support | UI behavior |
| --- | --- | --- | --- | --- |
| `profile_url` | URL string | Required, Douyin/iesdouyin host | Supported by source adapter identity normalization | Source field |
| `start_date` / `end_date` | ISO datetime | Start <= end | Supported with `date_mode=absolute_range` | Time range group |
| `min_views` / `max_views` | integer | Non-negative, min <= max | Supported from latest metric snapshot | Core metrics group |
| `min_likes` / `max_likes` | integer | Non-negative, min <= max | Supported from latest metric snapshot | Core metrics group |
| `min_comments` / `max_comments` | integer | Non-negative, min <= max | Supported from latest metric snapshot | Audience signal group |
| `min_shares` / `max_shares` | integer | Non-negative, min <= max | Supported from latest metric snapshot | Audience signal group |
| `min_duration_seconds` / `max_duration_seconds` | float | Non-negative, min <= max | Supported from `SourceVideo.duration_seconds` | Processing fit group |
| `min_engagement_rate` / `max_engagement_rate` | float | 0-1, min <= max | Supported by computing `(likes + comments + shares) / views` | Audience signal group |
| `has_speech` | any/yes/no | Enum | Supported from `metadata_json.has_speech`; `any` omits filter | Processing fit group |
| `max_text_density` | low/medium/high/any | Enum | Supported from `metadata_json.text_density` | Processing fit group |
| `exclude_heavy_watermark` | boolean | Boolean | Supported from `metadata_json.has_heavy_watermark` | Processing fit group |
| `exclude_high_processing_complexity` | boolean | Boolean | Supported from `metadata_json.processing_complexity in high/blocking` | Processing fit group |
| `exclude_high_copyright_risk` | boolean | Boolean | Supported from open high/blocking copyright risk flags | Risk guardrail group |

## Deferred Fields

| Field | Reason |
| --- | --- |
| `speech_density` | No normalized metadata field or filter logic exists yet. |
| `watermark_level` | Backend currently supports only heavy watermark boolean. |
| `risk_level` | Existing filter only checks high/blocking copyright risk, not generic aggregate severity. |
| `content_type` | No normalized source-video metadata contract yet. |
| `commercial_intent` | No normalized metadata or scoring/filter contract yet. |

## Response Additions

`POST /intake/discover` should include:

- existing success/session/candidate counts
- `filters_applied_summary`: serialized effective filter config after preset merge
- `unsupported_filters_ignored`: empty list for now because unsupported filters are not submitted by UI

## Defaults

- `min_views=10000`
- `min_likes=500`
- `preset_name=viral_discovery`
- comments/shares/duration/engagement/suitability filters are optional by default
