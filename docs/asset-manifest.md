# Asset Manifest

The asset manifest is the stable contract between download/storage and later media processing steps. OCR, STT, subtitle, TTS, and render stages should read the manifest instead of guessing file paths.

## Strategy

Phase 1 assembles the manifest dynamically from canonical DB records:

- `SourceVideo`
- `SourceProfile`
- current `MediaAsset` rows

The pipeline also writes a `METADATA_JSON` mirror file into storage for local debugging. The DB remains the source of truth for asset state.

## Shape

```json
{
  "manifest_version": "ASSET_MANIFEST_V1",
  "source_video": {
    "id": "video-uuid",
    "external_id": "7420000000000000000",
    "source_url": "https://example.test/video.mp4",
    "caption": "source caption",
    "posted_at": "2026-04-17T09:00:00+00:00",
    "duration_seconds": 24.5
  },
  "source_profile": {
    "id": "profile-uuid",
    "external_id": "douyin-profile-id",
    "display_name": "Creator"
  },
  "storage": {
    "provider": "local",
    "root": "./data/storage",
    "video_prefix": "workspace_x/douyin/profile_y/niche_default/video_z"
  },
  "assets": [
    {
      "id": "asset-uuid",
      "asset_type": "SOURCE_VIDEO_RAW",
      "status": "AVAILABLE",
      "version": 1,
      "is_current": true,
      "logical_key": "workspace_x/douyin/profile_y/niche_default/video_z/raw/v1_video.mp4",
      "storage_key": "workspace_x/douyin/profile_y/niche_default/video_z/raw/v1_video.mp4",
      "relative_path": "workspace_x/douyin/profile_y/niche_default/video_z/raw/v1_video.mp4",
      "mime_type": "video/mp4",
      "size_bytes": 123456,
      "checksum_sha256": "sha256",
      "source_url": "https://example.test/video.mp4",
      "created_at": "2026-04-17T09:01:00+00:00",
      "updated_at": "2026-04-17T09:01:00+00:00"
    }
  ]
}
```

## How Later Steps Use It

- Audio analysis finds `SOURCE_VIDEO_RAW` and later writes `SOURCE_AUDIO_EXTRACT`.
- OCR reads `SOURCE_VIDEO_RAW` or `SOURCE_VIDEO_PREVIEW`.
- Subtitle and render stages read current source assets and write new `MediaAsset` or `RenderOutput` records.
- Debug tools can show missing or failed optional assets without reading raw payloads.

## Current Asset Rules

Only current assets are included in the manifest. Historical versions remain in `MediaAsset` for trace/debug.

When a force refresh happens:

1. Existing current asset becomes `is_current = false`.
2. New asset gets `version = previous_version + 1`.
3. Manifest includes the new current asset only.

## Phase 1 Limits

- Manifest is not stored as a separate DB table.
- Manifest JSON files are not versioned independently.
- No object storage URL signing is included yet.
