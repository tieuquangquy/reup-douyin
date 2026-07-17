# Douyin Ready Check User Guide

## What It Is

Ready Check is a one-click summary before `/intake` that tells you whether a connected Douyin account is actually ready for discovery.

## Result Categories

- `READY`: run intake now with the connected browser profile.
- `READY_AFTER_REOPEN`: reopen the saved browser profile first, then run intake.
- `FALLBACK_READY`: intake can run with fallback conditions instead of the browser-primary path.
- `NOT_READY`: fix the account/profile state before running intake.

## What It Shows

- selected or recommended account
- account health
- browser profile/runtime status
- whether reopen is needed
- intended fetch path
- recommended next action

## What It Reuses

- account health
- watchdog/runtime status
- preflight cache
- fetch-path selection policy

It does not run a second discovery engine.

## What It Does Not Do

- It does not ingest profile videos.
- It does not create candidates.
- It does not replace validation or runtime reset.
- It does not expose cookies or secrets.
