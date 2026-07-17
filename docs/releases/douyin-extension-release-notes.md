# Douyin Extension Release Notes

Release: `0.1.0`

Release status: `ready_for_operator_trial`

## Summary

This release packages the feature-complete Douyin Current Tab Capture / Douyin Scanner extension for operator trial. The release focuses on final QA, packaging hygiene, installation handoff, rollback documentation, and known issue disclosure.

## Included capabilities

- MV3 extension popup for Douyin profile scanner operation.
- Local backend connection using default API base URL `http://127.0.0.1:8000`.
- Operator-editable API base URL in Advanced details.
- Current tab/profile scanning and Capture Inbox save flow.
- Whole Profile Harvest workflow with explicit operator controls.
- Safety handling for login/challenge/captcha checkpoints.
- Debug/maintenance controls remain explicit and user-triggered.

## Packaging changes

- Production build now cleans stale `dist` output before emitting files.
- Production build excludes source test files from emitted extension output.
- Release package command creates both unpacked and zip outputs.
- Package hygiene report is generated with release status and forbidden match results.

## Safety and scope notes

- No crawler behavior was added.
- No hidden auto-run behavior was added.
- Legacy harvest features remain disabled and guarded.
- Batch default remains safe and limited by existing scanner controls.
- The extension does not package secrets, local `.env` files, logs, screenshots, coverage, source maps, docs, or tests.

## Build and package outputs

- Build output: `apps/extension-douyin-capture/dist`
- Unpacked package: `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0`
- Zip package: `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0.zip`
- Hygiene report: `apps/extension-douyin-capture/release/package-hygiene-report.json`

## Validation summary

- Typecheck: passed.
- Tests: passed.
- Build: passed.
- Package: passed.
- Package hygiene: passed.
