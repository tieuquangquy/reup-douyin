# Douyin Extension Manual QA Checklist

Release: `0.1.0`

Use this checklist after package generation and before declaring operator trial complete.

## Package and installation

- [ ] Confirm `npm --workspace @reup-douyin/extension-douyin-capture run package` completes successfully.
- [ ] Confirm `apps/extension-douyin-capture/release/package-hygiene-report.json` has `package_hygiene_passed: true`.
- [ ] Confirm `forbidden_file_matches` is empty.
- [ ] Confirm `forbidden_pattern_matches` is empty.
- [ ] Load unpacked extension from `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0`.
- [ ] Confirm extension name is `Reup Douyin Current Tab Capture`.
- [ ] Confirm extension version is `0.1.0`.

## Backend connection

- [ ] Start the local backend.
- [ ] Open the extension popup.
- [ ] Open Advanced.
- [ ] Confirm API Base URL is `http://127.0.0.1:8000` or the intended local backend URL.
- [ ] Click Reconnect Douyin Tab after opening a supported Douyin page.
- [ ] Confirm API health status does not show a stale or unreachable backend after reconnect.

## Supported page detection

- [ ] Open a Douyin profile page.
- [ ] Open the extension popup.
- [ ] Confirm the profile health chip indicates a supported profile context.
- [ ] Confirm the primary action is Scan Profile or the next expected scanner action.

## Scanner workflow

- [ ] Run Scan Profile on a supported profile.
- [ ] Confirm a collection plan is built.
- [ ] Confirm counters for New, Incomplete, Already collected, and Queue are visible after scan.
- [ ] Confirm default collection settings show New + incomplete, Next 10, Safe.
- [ ] Run the next manual collection action only when operator-ready.
- [ ] Confirm pause/resume controls appear only when appropriate.
- [ ] Confirm Reset Scanner State remains an explicit operator action.

## Safety checkpoint behavior

- [ ] If Douyin shows login, captcha, or security challenge, confirm the scanner pauses or blocks safely.
- [ ] Confirm no hidden auto-run continues after a captcha/login/security checkpoint.
- [ ] Confirm operator instructions are visible in Advanced troubleshooting/safety tips.

## Backend save flow

- [ ] Confirm Save Flow displays scan session, save data, save 1 video, and save to Capture Inbox statuses.
- [ ] Save one item when available and verify Capture Inbox item creation.
- [ ] Save a batch only when the scanner indicates it is ready.
- [ ] Confirm failures show actionable error text instead of silent failure.

## Capture Inbox handoff

- [ ] Open Capture Inbox using the extension CTA.
- [ ] Confirm saved items appear in Capture Inbox.
- [ ] Confirm extension workflow does not directly modify Capture Inbox UI state outside the backend save handoff.

## Rollback readiness

- [ ] Keep the previous known-good extension package available before installing this release.
- [ ] Confirm rollback steps in `docs/releases/douyin-extension-rollback-guide.md` are understandable for the operator.

## Final decision

- [ ] No release blockers observed.
- [ ] Known issues reviewed.
- [ ] Release status remains `ready_for_operator_trial`.
