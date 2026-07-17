# Phase 12F Queue-Driven Smart Harvest Navigation Log

## Scope

This change is limited to `apps/extension-douyin-capture` Smart Capture & Harvest navigation behavior, tests, and this documentation note.

Non-goals:

- No crawler implementation.
- No video processing implementation.
- No backend schema or database changes.
- No automatic publish integration.

## Behavior

Smart Capture & Harvest now preserves the ordered captured profile targets as a `target_aweme_ids` queue. After extracting metrics for the current modal video and flushing when configured, the harvest loop selects the next unprocessed target from that queue.

Navigation order is now:

1. Extract the current modal metrics.
2. Queue the harvested item and flush if `flush_every_n_items` is reached.
3. Read the next unharvested and unfailed aweme id from `target_aweme_ids`.
4. Try direct routing by updating the modal URL to `modal_id=<next_aweme_id>`.
5. If direct routing does not move the modal, fall back to the restored automatic next-navigation sequence: visible next control, ArrowDown/PageDown, wheel, ArrowDown.
6. If the queued target remains stuck, record it in `failed_items` with `modal_navigation_stuck`.
7. Continue the batch with the next queued target instead of stopping the whole harvest for one stuck video.

## State and resume

`target_aweme_ids` is stored in both smart popup state and full modal harvest state so the queue survives pause/resume. Existing no-queue behavior remains compatible: if no queue is available, harvest falls back to normal automatic next-modal navigation and can still stop safely on navigation timeout.

## Operator expectation

For the normal profile-first workflow, run Smart Capture & Harvest on the profile page first so the extension captures the visible grid order. Then open a modal and resume/start harvest. The captured queue allows the harvest loop to skip individual stuck targets while preserving the batch.
