# Phase 5E-R Revalidate Operator Guide

## Manual login + revalidate workflow

### 1. Open the saved browser profile

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --open-profile --timeout-seconds 300
```

### 2. In that browser profile
- Open `https://www.douyin.com`
- Log in if needed
- Complete captcha/manual verification if shown
- Open one Douyin page manually to confirm access

### 3. Revalidate the account

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --revalidate --timeout-seconds 120
```

### 4. Rerun metadata hydration

```powershell
cd apps/api
python scripts/hydrate_capture_session_metadata.py --session-id a57e64d1-a7a8-48e0-b49a-199128b25740
```

## Success example
- `status = ACTIVE`
- `health_status = HEALTHY`
- `readiness_status = READY`

## Failure example
- `manual_login_required`
- `captcha_required`
- `profile_reopen_failed`
- `douyin_blocked`
