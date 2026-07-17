# Publish-Ready State

Publish-ready is the handoff marker from final review into publish draft and scheduling work.

## Strategy

Phase 1 stores the decision in two places with separate meanings:

- `RenderOutput.status = APPROVED` means a specific rendered file passed final quality review.
- `SourceVideo.status = PUBLISH_READY` means the video workflow is ready for publish draft preparation.

This keeps render quality approval separate from the product workflow state. A source video can have multiple render outputs over time, but only the latest reviewed output should be used to mark the video publish-ready.

`PublishDraft.status = READY` is a separate metadata readiness state. A video can be media-ready while its caption, CTA, hashtags, and schedule are still incomplete.

## API Actions

`POST /renders/{render_id}/approve`

- Valid from `READY_FOR_REVIEW` or already `APPROVED`.
- Sets `RenderOutput.status = APPROVED`.
- Adds `metadata_json.final_review.approved_at`.

`POST /renders/{render_id}/mark-publish-ready`

- Approves the render if needed.
- Sets `SourceVideo.status = PUBLISH_READY`.
- Adds `metadata_json.final_review.publish_ready_at`.

## Rerender Behavior

Creating and completing a new final render sets the source video back to `READY_FINAL_REVIEW`. That means publish-ready must be reconfirmed for the new output. This avoids a stale approval silently carrying over to a different file.

## Why Not Store Publish-Ready Only On RenderOutput?

Publish draft creation is a source-video workflow step, not only a file-level fact. Keeping the source video status as `PUBLISH_READY` makes the next step simple to query while preserving exact approval metadata on the chosen render output.

## Future Extension

For SaaS multi-user approval, this can evolve into an approval history table with actor, role, notes, and policy checks. Phase 1 intentionally avoids that complexity.
