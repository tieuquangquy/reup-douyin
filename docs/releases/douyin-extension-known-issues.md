# Douyin Extension Known Issues

Release: `0.1.0`

Release status: `ready_for_operator_trial`

## Known issues

### Manual installation is required

The release is an unpacked/zip package for local operator use. It is not distributed through the Chrome Web Store or Edge Add-ons.

Mitigation: follow `docs/releases/douyin-extension-install-guide.md`.

### Douyin layout changes may require recalibration

The scanner depends on browser-visible Douyin profile and modal layout. Douyin UI changes can make calibration or metric extraction fail.

Mitigation: use Advanced calibration controls and rerun manual QA on representative pages.

### Captcha, login, and security challenge pages require operator action

The extension does not auto-bypass captcha, login, or security challenge pages.

Mitigation: resolve the prompt manually in the browser, then resume only when safe.

### Local backend must be running

The extension defaults to `http://127.0.0.1:8000`. Save and status flows fail if the backend is stopped or running on a different URL.

Mitigation: start the backend and update Advanced API Base URL if needed.

### Debugger permission is required

The MV3 manifest includes `debugger` permission for CDP-backed extraction and runtime inspection flows.

Mitigation: operator must accept the permission during manual installation. This permission should be revisited before public distribution.

### Backend download endpoint packages current build output

The backend `GET /douyin-extension/download` endpoint packages the current extension `dist` output. It should be used only after a clean production build/package pass.

Mitigation: run `npm --workspace @reup-douyin/extension-douyin-capture run package` before using backend download for a release package.

## Release blockers

None observed in final automated Phase 22C-7 checks.
