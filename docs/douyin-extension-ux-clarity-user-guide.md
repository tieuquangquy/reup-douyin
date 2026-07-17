# Douyin Extension UX Clarity User Guide

## Real Capture Path

Use the browser extension popup for real current-page capture.

1. Build or download the extension artifact.
2. Load the extension manually in Chrome or Edge.
3. Open a supported Douyin page in the browser.
4. Open the extension popup.
5. Run `Check extension connection`.
6. Use `Detect current page` or `Capture current page` from the popup.

The manager labels this route with `Real capture via extension`.

## Manual Backend Test Path

The web manager form is for troubleshooting only. It does not read the active browser tab.

1. Open the advanced troubleshooting/manual backend testing section.
2. Enter safe page snapshot fields manually.
3. Use `Test detect from form` to validate backend page detection against the typed payload.
4. Use `Submit manual capture test` to validate backend capture handling against the typed payload.

The manager labels this route with `Manual backend test only`.

## What Changed

- The real extension popup path is visually primary.
- The backend manual form is secondary and collapsed by default.
- Manual form buttons use test-oriented labels rather than active-tab capture wording.

## Troubleshooting

If the extension popup cannot connect, verify the API server is running and the popup backend URL points to the local API. If a manual backend test succeeds but the popup fails, focus troubleshooting on browser extension permissions, active Douyin tab state, or extension reload status.
