# apps/web

Next.js + TypeScript frontend for the local operator experience.

## Responsibility

- Own operator-facing screens, review workflows, forms, and client-side interaction.
- Call `apps/api` for data, workflow actions, and job status.
- Keep browser-safe config separate from server-only config.

## Boundaries

- Do not crawl Douyin from the frontend.
- Do not process videos in the frontend.
- Do not write directly to PostgreSQL, Redis, local storage roots, or future object storage.
- Do not hardcode business workflow state that belongs to API or worker orchestration.

## Review Board

The first web screen is available at `/review-board`.

It loads candidates, filter presets, score breakdowns, and supports selection plus bulk keep/reject/mark-next-step actions.

## Transcript Editor

The transcript editing checkpoint is available at `/source-videos/[id]/transcript-editor`.

It loads current transcript and translation draft segments from the API, supports inline text/timing edits, merge/split actions, before/after comparison, dirty-state tracking, and save/discard/rerun flows.

## Final Review

The final render checkpoint is available at `/source-videos/[id]/final-review`.

It loads the latest `RenderOutput`, shows final/original comparison modes, render warnings, metadata, a local review checklist, and actions to approve export, rerender, or mark the source video publish-ready.

## Publish Draft

The publish preparation screen is available at `/source-videos/[id]/publish`.

It creates and edits platform-specific publish drafts for publish-ready videos, including caption, CTA, hashtags, placeholder account reference, planned publish time, and draft-ready actions.

## Current Status

Review board, transcript editor, final review, and publish draft UI foundations are available. No OCR editor, publish connector, real scheduler, auth, or dashboard has been implemented.
