# Phase 3G Batch Continuation UX Clarity

## Scope

Phase 3G adds minimal UI clarity for the successful safe-batch continuation state after `Start Collecting` processes a safe Next 10 batch and leaves more pending items.

## Safe continuation state

The continuation copy is shown only when all of the following are true:

- `phase === "batch_safe_mode_completed"`
- collection is idle / not actively collecting
- pending count is greater than zero
- failed count is zero, or the top failure is `none`
- the canonical scanner primary action remains `start_collecting`

## UI behavior

When the exact safe continuation state is present, the compact scanner UI changes only display copy:

- Primary button label: `Continue Next 10`
- Continuation message: `Batch complete: {saved_count} saved, {pending_count} remaining. Click Continue Next 10 to process the next batch.`

The counts are live state-derived counts. The UI does not hard-code the saved or pending count values.

## Dispatch behavior

The button keeps the existing canonical Start Collecting action key and path:

- action key remains `start_collecting`
- popup dispatch remains `start_collecting -> runWholeProfileHarvestProductFromPopup()`
- Resume is not used for safe-batch continuation
- no new action type was added

## State preservation

Phase 3G does not clear or mutate queue, calibration, pending items, session, or current index. It does not change scanner, auto-scroll, profile discovery, backend validation, payload schema, harvest item semantics, or Phase 3E profile-safe session verification.

## Diagnostics

No persistent diagnostics were added. The requested diagnostics were intentionally not written because Phase 3G is a display-only view-model clarification and adding storage writes for label visibility would expand runtime mutation surface unnecessarily.

## Tests

Focused coverage was added for:

- continuation message after `batch_safe_mode_completed` with pending items
- primary label `Continue Next 10`
- action key remaining `start_collecting`
- popup source dispatch staying on the existing Start Collecting path
- Resume not being used for safe-batch continuation
- queue, calibration, capture session, and current index preservation in the UI state
- no continuation label for completed zero-pending state
- no continuation label for failed state with a top failure

## Manual validation checklist

After loading the built extension:

1. Scan a profile with more than 10 eligible videos.
2. Confirm initial primary action is `Start Collecting`.
3. Click `Start Collecting` and wait for the safe batch to stop at the limit.
4. Confirm state shows `phase: batch_safe_mode_completed`, idle collection, and pending count greater than zero.
5. Confirm the primary button reads `Continue Next 10`.
6. Confirm the message reads `Batch complete: {saved_count} saved, {pending_count} remaining. Click Continue Next 10 to process the next batch.` with live counts.
7. Click `Continue Next 10` and confirm collection starts through the normal Start Collecting path, not Resume.
8. Confirm queue, calibration, capture session, pending items, and current index are preserved.
