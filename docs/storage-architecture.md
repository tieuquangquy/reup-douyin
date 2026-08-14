# Storage Architecture

`reup-douyin` uses a storage abstraction so media pipeline code does not depend on local disk paths. Phase 1 writes to local disk, but the service layer talks to a `StorageBackend` interface that can later be implemented by S3-compatible object storage or another cloud blob backend.

## Responsibilities

- `src/storage/base.py` defines the backend contract.
- `src/storage/local.py` implements local disk writes, existence checks, metadata reads, deletes, and key listing.
- `src/storage/path_strategy.py` owns logical key layout for video assets.
- `src/storage/manifest.py` assembles a manifest from canonical DB records.
- `src/storage/asset_health.py` validates existence, non-empty file size, and optional checksum.

Services above storage must pass logical keys into the backend. They should not join filesystem paths directly.

## Local Layout

Phase 1 stores authoritative assets under `LOCAL_STORAGE_ROOT`, defaulting to
`./data/storage`. The current logical-key strategy is profile-scoped and keeps
raw source videos easy to find:

```text
storage/
  workspace_{workspace_id}/
    dy/
      @{handle_or_nickname}__{profile_external_id_short}/
        {raw_filename}.mp4
        metadata/
          {aweme_id}__v{n}_source_metadata.json
          {aweme_id}__v{n}_caption.txt
        audio/
        ocr/
        cleaned/
        previews/
        renders/
```

`niche_{slug}` is inserted only when a niche is present. The profile label is
sanitized for Windows and falls back to `@user__{id}` when ingest has not yet
provided a handle or display name. The path includes workspace, platform,
profile, optional niche, and source-video identity, so it remains a valid object
storage prefix when the local backend is replaced.

Download transfer files do **not** live under authoritative storage. They use the
separate managed root `.douyin_profiles/download_staging_v2` (or the configured
override), namespaced by workspace/account/aweme/transfer id. This prevents a
partial transfer from being exposed through the asset manifest.

Set `DOUYIN_DOWNLOAD_STAGING_DIR` identically in the API and worker when a
custom location is required. The older
`DOUYIN_PLAYWRIGHT_DOWNLOAD_STAGING_DIR` name remains a deprecated compatibility
alias and is superseded when both values are present. Never use an
authoritative storage path as a staging override.

## Asset State

`MediaAsset` is the canonical asset index. It stores:

- `asset_type`
- `status`
- `storage_provider`
- `storage_key`
- `logical_key`
- `relative_path`
- `version`
- `is_current`
- `checksum_sha256`
- `size_bytes`
- `source_url`
- `created_by_job_id`

Absolute paths are local-only debug metadata and are kept inside `metadata_json`, not as the canonical address.

## Version and cache strategy

For the same `source_video_id + asset_type`, the current asset is the row where
`is_current = true`. A normal download reuses that row only after existence,
size, SHA-256, and (for raw video) ffprobe checks pass. A failed integrity check
is a cache miss, not a successful download.

- Sidecars use versioned filenames (`v{n}_...`) and retain historical rows when
  refreshed.
- The operator-facing raw source filename is not version-prefixed. Because
  storage keys are unique, a refresh that resolves to the same filename updates
  that row in place after atomic promotion; the database does not retain a
  second historical raw object for that case. If the resolved filename changes,
  a new row/key can be created. If complete byte-level raw history becomes a
  requirement, introduce a content/version suffix and a separate
  `source_download` lineage before promising it.
- Failed optional assets can create a current `FAILED` record so the manifest
  explains what happened without hiding a usable primary video.

`force_refresh` is an explicit replacement command, not a general retry flag.
Queue retries normally keep it false so a verified source is not downloaded a
second time.

## Integrity and promotion boundary

The downloader writes to a staging file using bounded streaming/Range resume (or
yt-dlp's `.part` file). The service then validates the completed media with
`ffprobe`, computes SHA-256, and promotes it atomically into the logical key.
`MediaAsset` is updated only after the promoted file has a positive size. A
crash before promotion leaves a non-authoritative staging artifact that can be
resumed or expired; it cannot appear as an available manifest asset.

## Lifecycle and Phase 1 limits

- A worker housekeeping sweep removes expired files from the managed download
  staging root according to `DOUYIN_DOWNLOAD_STAGING_TTL_HOURS` (24 hours by
  default). It removes empty staging directories only; authoritative storage is
  not recursively swept by this download cleanup.
- The legacy flat `.douyin_profiles/download_staging` directory is intentionally
  outside that sweep because old regression manifests can reference completed
  source files there. Retire it only through an explicit, operator-verified
  migration after all references have been moved to the v2 namespace or
  authoritative storage.
- Regenerable downstream artifacts have a separate, opt-in retention sweep
  (`ARTIFACT_RETENTION_ENABLED=false` by default).
- No cloud backend, signed URL generation, or object-store lifecycle policy is
  implemented yet.
- Storage is intended for one local operator, but logical keys and DB records are
  workspace-scoped for SaaS readiness.
