# Phase 17R Target Validation Operator Guide

## Purpose

Use Modal Whole Profile Test to verify that the extension can resolve a modal video back to the profile, build a clean accepted target queue, and dry-run selected targets before production harvest is enabled.

## Verify-only Flow

1. Open a Douyin modal video on the target profile.
2. Open the extension popup.
3. Expand Advanced Diagnostics.
4. Select `Verify only`.
5. Click `Test Modal → Whole Profile Harvest`.
6. Review the Modal Whole Profile Test panel.

Expected safe result:

```text
Profile scan: success
Total candidates: X
Accepted targets: Y
Rejected: Z
Target count: Y
Backend writes: none
Can harvest whole profile: yes
```

`Target count` now counts accepted video targets only. Rejected examples are shown separately and do not enter the target queue.

## Rejected Candidate Examples

Rejected examples use this format:

```text
202605050200442800701 · likely_timestamp · body_regex
```

Common reasons:

- `invalid_length`: not a numeric 16-22 digit candidate.
- `likely_timestamp`: resembles `YYYYMMDD...` or generated date/time state.
- `unscoped_regex`: came from body-level regex without card/video context.
- `no_video_context`: appeared in footer/legal/contact or without a card/link/video container.
- `duplicate`: already accepted from stronger evidence.

## Dry-run Sampling Modes

After Verify-only completes successfully, use one of these modes without rescanning:

- `Dry-run first 3 videos`: opens the first accepted targets.
- `Dry-run last 3 videos`: opens the last accepted targets.
- `Dry-run random 3 videos`: opens a stable random sample from accepted targets only.
- `Dry-run specific aweme IDs`: opens only pasted IDs that exist in the accepted queue.

For specific IDs, paste comma-separated or newline-separated aweme IDs into the `Specific aweme IDs for dry-run` field.

## Safety Guarantees

Dry-run does not write Tile Gallery items, does not create Capture Inbox rows, does not touch production Smart Capture state, and does not call `/douyin-extension/full-modal-harvest`. It writes only the isolated `douyinModalWholeProfileTestRun` runtime.

## Live Retest Steps

1. Reset Modal Test.
2. Open a profile modal URL.
3. Run `Verify only`.
4. Confirm suspicious timestamp-like candidates are rejected.
5. Confirm `Accepted targets` equals `Target count`.
6. Run `Dry-run first 3 videos`.
7. Run `Dry-run last 3 videos`.
8. Run `Dry-run random 3 videos`.
9. Paste known accepted IDs and run `Dry-run specific aweme IDs`.
10. Confirm each dry-run row shows matching target/current/extracted aweme IDs and `No backend writes performed`.
