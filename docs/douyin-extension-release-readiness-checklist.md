# Douyin Extension Release Readiness Checklist

## Required automated checks

- [ ] Extension test suite passes: `npm --workspace @reup-douyin/extension-douyin-capture run test`
- [ ] Extension typecheck passes: `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- [ ] Extension build passes: `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Operator workflow checks

- [ ] Scan Profile discovers expected profile videos.
- [ ] Classification separates collect, skip, incomplete, and retry targets.
- [ ] Calibration state remains stable across popup refresh.
- [ ] Start Collecting processes only the safe batch limit.
- [ ] Batch Next 10 does not process a full profile automatically.
- [ ] Retry/incomplete/skip-completed policy is visible in counters.
- [ ] Captcha/checkpoint pause shows an operator-friendly Vietnamese message.
- [ ] Resume continues only after the operator resolves the Douyin tab state.
- [ ] Reset current run clears active locks and current transient run state.
- [ ] Reset current run preserves calibration, settings, backend session, queue, results, and backend data.

## Diagnostics checks

- [ ] Run summary contains run/session/profile IDs, counts, stop reason, safety status, and next action.
- [ ] Recent item results show at most 10 safe item summaries.
- [ ] Error category mapping includes retryable/stop/next-action decisions.
- [ ] Counter invariant uses canonical queue counts.
- [ ] Advanced diagnostics copy includes `hardening_diagnostics`.
- [ ] Advanced diagnostics copy includes sanitized `export_report`.
- [ ] Export report excludes tokens, cookies, auth headers, raw DOM, raw script, raw payloads, debug payloads, and secret-like fields.

## Release gates

- [ ] No legacy runner calls are reachable from production controls.
- [ ] No batch limit increase was introduced.
- [ ] No backend save contract rewrite was introduced.
- [ ] No Capture Inbox frontend redesign was introduced.
- [ ] Remaining risks are documented in the release report.
