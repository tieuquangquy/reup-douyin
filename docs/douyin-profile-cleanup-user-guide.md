# Douyin Profile Cleanup User Guide

## What It Does

Douyin profile cleanup scans local browser profile directories, keeps one canonical profile per account, and moves old duplicate/orphan profiles into quarantine.

## What It Does Not Do

- It does not delete profiles permanently.
- It does not delete Douyin accounts.
- It does not read or display cookies.
- It does not decide whether a profile is logged in.
- It does not create a new browser profile.

## Recommended Flow

1. Run a dry-run scan.
2. Review canonical, orphan, duplicate, and active profile counts.
3. Apply cleanup only when the plan is acceptable with:

```json
{ "dry_run": false, "apply": true }
```

4. Reopen the account profile from `/accounts/douyin` and validate.

## Safety Rules

- Canonical account-linked profiles are kept.
- Runtime-active profiles are skipped.
- Noncanonical profiles are quarantined under `_quarantine`.
- Hard delete is intentionally not implemented in V1.

## Current Local Cleanup Result

The local cleanup run moved 7 old duplicate connect-session profiles into `_quarantine/20260423T164322Z`. The top-level active profile namespace now has 6 canonical profiles and no duplicate/orphan cleanup candidates.

## When To Use

Use this when previous broken browser-connect behavior created many profile directories and reconnect/retry behavior became confusing.

## When Not To Use

Do not use cleanup as a substitute for `Reset runtime state`. Cleanup handles local profile directory inventory; reset handles stuck runtime/session state.
