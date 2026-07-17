# Intake Productivity User Guide

## Purpose
`/intake` now includes productivity helpers to reduce repeated setup while keeping discovery explicit and operator-controlled.

## What Was Added
- **Saved presets**: store profile URL + filter setup + refresh mode for reuse.
- **Recent profiles**: quick-fill from recently discovered profiles in the workspace.
- **Latest successful fetch shortcuts**: quick-fill from recent completed crawl sessions.

## Important Guardrail
Using any shortcut or preset only **fills the form**. Discovery still runs only when you click **Discover candidates**.

## How To Use

### 1) Save current setup as preset
1. Fill profile URL, filters, and account/refresh options.
2. Click **Save as preset**.
3. Enter a unique preset name.
4. Reuse later from the **Saved presets** panel.

### 2) Apply saved preset
1. In **Saved presets**, click **Apply** on the preset.
2. Review fields filled into the form.
3. Click **Discover candidates** when ready.

### 3) Rename or delete saved preset
- Click **Rename** to change the preset label.
- Click **Delete** to remove the preset.

### 4) Use recent profile
1. In **Recent profiles**, click **Use profile**.
2. Confirm form values.
3. Submit discovery explicitly.

### 5) Use latest successful fetch shortcut
1. In **Latest successful fetches**, click **Use latest success**.
2. This fills profile URL from a recent successful crawl session.
3. Adjust filters if needed, then submit discovery.

## Built-in Presets vs Saved Presets
- **Built-in presets** tune filter thresholds only.
- **Saved presets** persist a complete intake setup (including profile URL and refresh/account context).

## Failure/Empty States
- If no saved presets/recent profiles/latest-success entries exist, each panel shows an empty-state message.
- If intake bootstrap fails, core discover flow remains available.

## Data Source and Boundaries
- Discovery remains canonical through existing intake discovery flow.
- Recent and latest-success panels are derived from canonical `SourceProfile`/`CrawlSession` history.
- Saved presets are persisted in `intake_saved_presets` and exposed via intake productivity endpoints.

## Verification Performed
- `npm run typecheck`
- `npm --workspace @reup-douyin/web run test`
- `set PYTHONPATH=apps/api&& python -m unittest apps/api/tests/test_intake_productivity_service.py -v`
- `set PYTHONPATH=apps/api&& python -m unittest discover -s apps/api/tests -p "test_intake_discovery_service.py"`
