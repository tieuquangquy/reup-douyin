# Phase 22C-7 Final QA, Packaging, and Production Handoff Resume

## Current status

Phase 22C-7 is complete and the Douyin extension release is ready for operator trial.

## Important outputs

- Build output: `apps/extension-douyin-capture/dist`
- Unpacked release package: `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0`
- Zip release package: `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0.zip`
- Package hygiene report: `apps/extension-douyin-capture/release/package-hygiene-report.json`
- Manual QA checklist: `docs/releases/douyin-extension-manual-qa-checklist.md`
- Release notes: `docs/releases/douyin-extension-release-notes.md`
- Install guide: `docs/releases/douyin-extension-install-guide.md`
- Rollback guide: `docs/releases/douyin-extension-rollback-guide.md`
- Known issues: `docs/releases/douyin-extension-known-issues.md`

## Checks completed

- Typecheck passed.
- Full extension test script passed.
- Production build passed.
- Release package command passed.
- Package hygiene passed with no forbidden file matches and no forbidden pattern matches.

## Commands to rerun

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run build
npm --workspace @reup-douyin/extension-douyin-capture run package
```

Or run the full final gate:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run typecheck && npm --workspace @reup-douyin/extension-douyin-capture run test && npm --workspace @reup-douyin/extension-douyin-capture run build && npm --workspace @reup-douyin/extension-douyin-capture run package
```

## Operator next step

Load `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0` as an unpacked extension in Chrome or Edge and complete the manual QA checklist.
