# Phase 5F Captcha-Aware Hydration Operator Guide

## What happens now
- Backend metadata hydration does not bypass captcha.
- If Douyin shows a captcha/challenge/block page for a video detail URL, hydration stops safely and returns:
  - `captcha_required`
  - the selected account id
  - the open-profile command to run next

## Manual operator steps
1. Open the saved Douyin browser profile:

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id <account_id> --open-profile --timeout-seconds 300
```

2. In the opened browser profile:
   - go to `https://www.douyin.com`
   - log in if needed
   - complete captcha/manual verification if shown
   - open one `https://www.douyin.com/video/<aweme_id>` page manually to confirm access

3. Rerun hydration:

```powershell
cd apps/api
python scripts/hydrate_capture_session_metadata.py --session-id <capture_session_id>
```

## What the system will not do
- It will not solve captcha automatically.
- It will not rotate proxies/accounts.
- It will not invent metadata from DOM text.

## Useful commands

### Check account readiness

```powershell
cd apps/api
python scripts/douyin_account_readiness.py
```

### Include archived/deleted accounts for audit

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --include-deleted
```
