# Phase 8A CDP DOMSnapshot Right-Rail Operator Guide

## Purpose

Phase 8A makes CDP DOMSnapshot layout extraction the only normal source for Douyin modal action metrics in Probe and Full Modal Harvest.

This reduces false positives from captions, chapter text, profile-grid numbers, player controls, and brittle selector/icon fallbacks.

## Before using

1. Confirm the local backend is running.
2. Confirm the extension is built and loaded in Chrome.
3. Open Douyin in the target Chrome profile.
4. Open a modal video on the active Douyin tab.

## Probe workflow

1. In the extension popup, attach CDP to the active Douyin tab.
2. Run Probe.
3. Continue only if Probe reports `PASS`.

A valid Phase 8A PASS should show:

- source `cdp_dom_snapshot_right_rail`;
- detected `aweme_id`;
- active video duration;
- like/comment/favorite/share counts;
- snapshot text count;
- compact label count;
- right-rail region;
- selected snapshot labels.

## Full Modal Harvest workflow

1. Run Probe and confirm PASS.
2. Start Full Modal Harvest.
3. Watch pending/flushed/updated counts.
4. Flush manually if needed before stopping.
5. Resume only from persisted controller state when the popup reports resumable progress.

Full Modal Harvest will only persist items that pass the same DOMSnapshot right-rail extraction gate as Probe.

## PASS/WARN/FAIL meanings

### PASS

The extension detected the active modal video, captured a DOMSnapshot, selected exactly four right-rail compact count labels, and extracted duration plus all four action metrics.

### WARN

A snapshot was captured, but labels were insufficient or ambiguous. Common causes:

- fewer than four compact labels in the right rail;
- more than one plausible group of four labels;
- right-rail geometry not matching the current modal layout.

WARN items are not harvested by Full Modal Harvest.

### FAIL

A blocking prerequisite is missing. Common causes:

- no current `aweme_id`;
- CDP snapshot unavailable;
- duration missing.

FAIL items are not harvested by Full Modal Harvest.

## Troubleshooting

### Probe says `cdp_snapshot_unavailable`

- Attach CDP again from the popup.
- Confirm the active tab is a Douyin tab.
- Refresh the modal page if Chrome detached the debugger.
- Re-run Probe after the modal video is visible.

### Probe warns about fewer than four labels

- Confirm the right rail is visible.
- Move the mouse away from overlays or player controls.
- Wait for modal UI to settle.
- Re-run Probe.

### Probe warns about ambiguous labels

- Confirm captions, comments, or side panels are not overlaying the right rail.
- Re-run after closing any additional overlays.

### Counts look wrong

Do not start Full Modal Harvest. Capture the Probe diagnostics, including:

- snapshot text count;
- compact labels found;
- right-rail region;
- selected snapshot labels;
- rejected examples.

Use those diagnostics to adjust geometry or rejection rules in a follow-up patch.

## Safety notes

- The extension must never log cookies, credentials, tokens, or private account material.
- Full Modal Harvest should keep stable identifiers in logs, including `aweme_id` and harvest id.
- Repeated flushes should remain idempotent and should update existing backend items by exact `aweme_id`.

## Verification commands

For developer verification:

```text
npx tsx apps/extension-douyin-capture/src/modalHarvest.test.ts
npm run typecheck --workspace apps/extension-douyin-capture
npm test --workspace apps/extension-douyin-capture
```

The first two commands were run successfully for Phase 8A. The full extension test script is recommended before packaging or release because it also builds the extension.
