# Data Model Overview

This document describes the first production-minded domain schema for `reup-douyin`. The schema is built for Phase 1 local operation while keeping tenant, worker, storage, and publishing boundaries ready for SaaS expansion.

## Design Principles

- Every core table has `id`, `created_at`, and `updated_at`.
- Most product tables include `workspace_id` now, even though Phase 1 has one local workspace.
- External Douyin identifiers are deduped by platform plus external id.
- Long-running work is represented by durable `jobs` and `job_steps`, not hidden request-side work.
- Local files are represented as `media_assets` with provider/key fields so local disk can later become object storage.
- JSON fields are used for raw provider payloads, tool output, evidence, or flexible settings where the exact structure is not stable yet.

## Entity Groups

### SaaS-Ready Foundation

| Table | Purpose |
| --- | --- |
| `workspaces` | Tenant/work boundary. Phase 1 uses one local workspace; future multi-user features can attach users and billing here. |
| `niche_tags` | Workspace-scoped tags for categorizing source profiles or video candidates later. |
| `workflow_templates` | Placeholder for future configurable workflows without hardcoding pipeline shape into infrastructure. |

### Source Ingestion

| Table | Purpose |
| --- | --- |
| `source_profiles` | External source profile, starting with Douyin. Dedupe uses `source_platform + source_profile_external_id`. |
| `crawl_sessions` | One crawl attempt against a source profile with status, timing, counts, and raw/debug payload. |
| `source_videos` | Canonical source video record. Dedupe uses `source_platform + source_video_external_id`. |
| `video_metric_snapshots` | Metrics observed during a crawl session, deduped by `source_video_id + crawl_session_id`. |

### Review And Candidate Pipeline

| Table | Purpose |
| --- | --- |
| `video_candidates` | One current candidate record per source video with score, status, priority, and notes. |
| `video_review_decisions` | Review decisions made at checkpoints. Multiple records allow history over time. |
| `risk_flags` | Structured warnings for copyright, watermark, duplicate, quality, policy, or manual review concerns. |

### Media And Render Outputs

| Table | Purpose |
| --- | --- |
| `media_assets` | Storage abstraction for source files, thumbnails, subtitles, rendered files, and export packages. |
| `render_outputs` | Render attempt/output metadata linked to a source video and optionally a final media asset. |

### Job Orchestration

| Table | Purpose |
| --- | --- |
| `jobs` | Durable unit of background work with type, status, attempts, lock fields, references, input, and result. |
| `job_steps` | Ordered sub-steps for traceability, retry, resume, and UI progress. |

### AI Editable Artifacts

| Table | Purpose |
| --- | --- |
| `transcript_segments` | Timecoded source-language transcript text with review status and versioning. |
| `translation_segments` | Translated text tied to transcript segments and language/version. |
| `subtitle_segments` | Render-ready subtitle text and style metadata. |
| `ocr_text_objects` | Normalized OCR text objects detected across video frames. |
| `ocr_frame_detections` | Frame-level bounding boxes and confidence for OCR evidence/debugging. |

### Publish Preparation

| Table | Purpose |
| --- | --- |
| `publish_drafts` | Platform-specific title, caption, hashtags, and payload preparation before publishing integration exists. |

## Relationship Summary

```text
Workspace
  -> SourceProfile
      -> CrawlSession
      -> SourceVideo
          -> VideoMetricSnapshot
          -> VideoCandidate -> VideoReviewDecision
          -> RiskFlag
          -> MediaAsset -> RenderOutput
          -> TranscriptSegment -> TranslationSegment -> SubtitleSegment
          -> OcrTextObject -> OcrFrameDetection
          -> PublishDraft

Job
  -> JobStep
  -> optional SourceVideo / CrawlSession / RenderOutput reference
```

## SaaS-Ready Decisions

- `workspace_id` appears throughout the schema so user/workspace ownership can be added without reshaping all core tables.
- There is no `users` table yet. Phase 1 does not need auth, but `workspace_id` keeps the data model open for users, roles, and billing.
- `media_assets.storage_provider` and `storage_key` avoid hardcoding local disk paths into product tables.
- `jobs.reference_type` and `reference_id` support future job references while explicit nullable foreign keys cover the known core objects.
- `workflow_templates` exists as a real table to keep future workflow customization out of hardcoded worker infrastructure.

## Current Limits

- No crawler, queue runner, API endpoint, or worker execution has been implemented.
- No auth, billing, or multi-user tables exist yet.
- No business validation is encoded in models beyond basic constraints and enums.

