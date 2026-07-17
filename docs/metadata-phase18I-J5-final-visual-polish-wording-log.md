# Phase 18I-J5 Final Visual Polish And Wording Log

## Friendly wording map

Main popup wording was changed from technical workflow language to operator language:

- Verify Profile -> Scan Profile
- Dry-run Random 3 -> Test 3 Random Videos
- Run Extraction -> Extract Next N
- Prepare Backend Session -> Create Save Session
- Build Payload Preview -> Check Save Data
- Payload Guard -> Data Check
- Flush One Item -> Save 1 Video
- Flush Batch -> Save Batch
- Backend -> Capture Inbox

Technical terms still remain in Debug / Technical Details where they are useful for debugging.

## Button hierarchy

- Primary blue:
  - Scan Profile
  - Extract Next 10
  - Resume
- Secondary gray:
  - calibration/test controls
  - Test First 3 / Test Last 3 / Test 3 Random Videos
  - Create Save Session
  - Check Save Data
  - Save 1 Video
- Warning orange:
  - Save Batch
  - Stop
- Danger outline:
  - Reset Harvest

## Error copy changes

Main status messages now map common technical failures into operator wording:

- payload guard failed -> Data check failed
- backend secret guard rejected -> Save was blocked by backend safety checks
- modal navigation timeout -> Could not open the video modal in time
- captcha detected -> Douyin security check detected; solve it manually then Resume
- profile grid not ready -> Could not find the profile video grid
- capture session create failed -> Could not create a Save Session

Raw codes remain available in Debug / Technical Details.

## Empty and success states

Empty-state wording is now operator-friendly:

- No videos queued yet. Scan Profile first.
- No metrics extracted yet. Run Extract Next 10 after a successful test.
- No saved videos yet.

Success-state wording now includes:

- Profile scanned. X videos found.
- Test passed. X videos read successfully.
- Metrics extracted. Ready to save.
- 1 video saved to Capture Inbox.
- Batch saved. Open Capture Inbox to review.

## Technical Details split

- Advanced Diagnostics -> Technical Details
- Details -> Debug Details

Main UI stays short; debugging data remains available without changing harvest logic.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Remaining UX ideas

- optional inline tooltip for Save Session / Save Data terms
- clearer row-level save verification summaries
- optional direct Capture Inbox deep-link when route ownership is confirmed
