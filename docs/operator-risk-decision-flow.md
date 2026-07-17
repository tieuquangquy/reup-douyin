# Operator Risk Decision Flow

Operator risk decisions are explicit checkpoint records. They do not replace final review, publish-ready state, or publish draft readiness.

## Decisions

- `CONTINUE`: operator reviewed warnings and proceeds.
- `NEEDS_FIX`: operator should return to an editor or rerun a pipeline.
- `REJECT`: operator rejects the target for now.
- `ACCEPT_WITH_WARNING`: operator intentionally overrides a warning and continues.

## Gate Rules

Phase 1 gate rules:

- `CRITICAL` or `BLOCKING` active warnings block continuation unless latest decision is `ACCEPT_WITH_WARNING`.
- `HIGH` active warnings require an operator decision.
- `LOW` and `MEDIUM` warnings do not block, but should remain visible.
- `RESOLVED` and `WAIVED` warnings are not active blockers.

These rules are operator-assist policy, not enterprise compliance.

## Final Review

Final review shows risk summary for the current `RenderOutput`.

`Approve export` still means the file is technically acceptable. It does not mean the output has no risk.

`Mark publish-ready` checks risk gate before setting `SourceVideo.status = PUBLISH_READY`.

## Publish Draft

Publish draft page shows risk summary for the `PublishDraft`.

`Mark draft ready` checks risk gate before setting `PublishDraft.status = READY`.

This keeps media readiness and publish metadata readiness separate:

- media-ready: `SourceVideo.status = PUBLISH_READY`
- metadata-ready: `PublishDraft.status = READY`

## Accept With Warning

`ACCEPT_WITH_WARNING` is an explicit operator override. It means the warning is understood and the operator chooses to continue. It should include a note when used for real work.

## Phase 1 Limits

- No legal review workflow.
- No multi-user approvals.
- No external moderation API.
- No AI image/video moderation.
- No automatic platform policy enforcement.
