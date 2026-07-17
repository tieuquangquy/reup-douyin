# Douyin Extension UX Clarity Architecture

## Decision

The Douyin Extension Manager should present the browser extension popup as the primary real capture surface. The web manager manual form is retained as a secondary troubleshooting tool for safe backend contract checks.

## Boundaries

### Web UI

The web app owns the operator-facing layout, labels, badges, and help text. It may call existing API wrapper functions for manual tests, but it must not imply that typed form values are active-tab browser capture.

### Extension Popup

The extension popup owns real active-tab current-page actions. Its `Detect current page` and `Capture current page` labels remain appropriate because those actions execute against the current Douyin tab.

### API

The API continues to expose existing detect and capture endpoints. No response model, request model, or route behavior changes are required for this UX clarification.

## UX Model

- Primary path: install/load extension, connect it to the backend, open Douyin in the browser, then run current-page actions from the extension popup.
- Secondary path: expand an advanced troubleshooting area and submit typed safe page fields to validate backend detect/capture behavior.

## SaaS-ready Considerations

This change keeps product workflow semantics at the web application layer and preserves API contracts. The distinction between real capture and manual testing avoids baking local single-operator assumptions into backend behavior.

## Risks

- If the manual form remains visually prominent, operators may still mistake it for the primary capture path.
- If button labels remain identical to popup labels, operators may assume both perform active-tab capture.

## Mitigations

- Use explicit badges for both surfaces.
- Collapse the manual backend form by default.
- Use test/debug wording for all manual backend form copy.
