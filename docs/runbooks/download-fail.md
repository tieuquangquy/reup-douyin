# Download Fail Runbook

## Symptoms

- `DOWNLOAD_VIDEO` job fails.
- `MediaAsset.status = FAILED`.
- Asset manifest is missing `SOURCE_VIDEO_RAW`.

## Common Causes

- `source_url` missing or unreachable.
- Storage root not writable.
- Downloader returned empty content.
- Checksum/size validation failed.

## Checks

- `GET /source-videos/{source_video_id}/asset-manifest`.
- `GET /source-videos/{source_video_id}/assets`.
- Job step around `fetch_primary_video`, `fetch_thumbnail`, or `register_assets`.
- Local storage root from API `.env`.

## Immediate Handling

- If source URL is missing, return to ingest/source metadata.
- If file write failed, fix `LOCAL_STORAGE_ROOT` permissions.
- If only thumbnail fails but source video exists, document partial state before rerun.

## Rerun / Decision

- Rerun with refresh when asset is corrupted or missing.
- Mark needs_fix if metadata points to wrong source URL.
- Reject if the source video is no longer accessible.
