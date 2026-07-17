# Phase 22C-9K - Scan Profile Success Diagnostics and Queue Contract Log

## Scope
- Cleaned up Scan Profile success diagnostics without changing the working scan algorithm.
- Preserved Start Collecting, pause/resume/reset, backend flush, modal extraction, Capture Inbox, Review Board, and payload contracts.

## Changes
- Updated active Scan Profile runtime diagnostics to 22C-9K across controller, popup, background, and content-script trace acceptance.
- Added DOM probe status normalization so ok plus completed timestamp displays as completed, failures remain failure/timeout, and missing attempts show not_attempted.
- Added profile count contract diagnostics: discovered, normalized, duplicate, invalid, already collected, eligible, queue total, batch limit, batch pending, batch mode, and queue limit reason.
- Enhanced operator diagnostics in the progress view model and text progress summary to show count contract fields and clearer DOM probe status.

## Queue Semantics Decision
- Preserved the canonical scan queue behavior.
- Start Collecting selects the next actionable targets from the stored queue through selectNextActionableTargets, so Scan Profile does not rewrite Start Collecting behavior.
- Queue/pending can be lower than discovered when the current queue is limited by the selected batch and speed settings; diagnostics now explain that with profile_queue_limit_reason.

## Validation
- Typecheck was run during implementation and passed.
- Full test and build validation are recorded in the final task result.
