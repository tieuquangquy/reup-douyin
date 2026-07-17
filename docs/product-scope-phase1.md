# Product Scope: Phase 1

Phase 1 is a local-first workflow for one Windows operator. The goal is to build reliable operator-assisted reupload preparation before investing in multi-user SaaS features.

## Target Workflow

1. Operator enters one or more Douyin profile links.
2. System crawls available videos from those profiles.
3. System filters and scores videos that may be worth reuploading.
4. Operator reviews candidates through a UI card/player workflow.
5. System runs semi-automated Vietnamese localization and video preparation.
6. Operator edits or approves important checkpoints.
7. System exports videos for multiple target platforms.

## Phase 1 Constraints

- Single operator.
- Windows local machine first.
- Local disk storage through a future-proof abstraction.
- PostgreSQL target for persistence.
- Redis target for queueing.
- Manual checkpoints are expected and should be explicit.
- Reliability and correctness matter more than speed.

## Out Of Scope For Bootstrap

- Douyin crawler implementation.
- Video download and processing.
- Filtering and scoring logic.
- UI card/player implementation.
- Database schema and migrations.
- Queue workers and retry implementation.
- Multi-user auth.
- Cloud storage.
- Auto publishing.

## Future SaaS Readiness

Phase 1 design should avoid hard assumptions that block:

- Multiple users and workspaces.
- Distributed queues and multiple workers.
- Cloud object storage.
- Job dashboards and audit logs.
- Automated publishing integrations.

