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

Phase 1 stores assets under `LOCAL_STORAGE_ROOT`, defaulting to `./data/storage`.

```text
storage/
  workspace_{workspace_id}/
    douyin/
      profile_{source_profile_external_id}/
        niche_default/
          video_{source_video_external_id}/
            raw/
            audio/
            metadata/
            temp/
            previews/
            renders/
```

The path includes workspace, source platform, source profile, niche placeholder, and source video. This is readable during local debugging while still mapping cleanly to object storage keys later.

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

## Version Strategy

For the same `source_video_id + asset_type`, the current asset is the row where `is_current = true`.

- Normal download reuses an existing current asset if the file still exists.
- `force_refresh=true` marks the previous current asset as non-current and writes a new version.
- Failed optional assets can create a current `FAILED` record so the manifest explains what happened.

This keeps re-downloads traceable without overwriting old debug evidence.

## Phase 1 Limits

- No cloud backend is implemented yet.
- No object lifecycle cleanup is implemented yet.
- No signed URL generation is implemented yet.
- Storage is intended for one local operator, but logical keys and DB records are workspace-scoped for SaaS readiness.
