# Phase 13G Flush Troubleshooting Guide

## What Changed

Smart Capture & Harvest now treats backend flush as a durable transport step. If the Douyin extension extracts metrics but cannot reach the local backend, it preserves pending items and shows a backend-specific error code plus next action.

## Error Codes

- `backend_unreachable`: the backend health check failed. Start or restart the local API, then retry flush.
- `cors_or_permission_blocked`: the backend health check succeeded but the flush fetch looked blocked by CORS or extension host permission rules. Reload the extension after manifest changes and verify backend CORS configuration if needed.
- `request_timeout`: the request timed out. Check whether the API is overloaded or blocked, then retry.
- `http_422_schema_error`: the backend rejected the payload schema. The item is preserved, but this is terminal until the payload/API contract is fixed.
- `http_500_server_error`: the backend returned a server error. Restart or inspect API logs, then retry.
- `http_4xx_client_error`: the backend returned another client error. Inspect the response and payload contract before retrying.
- `network_failed`: browser transport failed without a more specific diagnosis. Check backend availability, localhost permissions, and extension reload state.

## Operator Recovery Steps

1. Keep the Douyin tab open.
2. Start or restart the local backend at `http://127.0.0.1:8000`.
3. Open the extension popup.
4. Review the flush diagnostic lines:
   - `Flush failed`
   - `Flush URL`
   - `HTTP status`
   - `Pending preserved`
   - `Retryable`
   - `Next action`
5. Click the flush/retry pending action after the backend is healthy.
6. Confirm pending count decreases and the last flush status becomes `success`.

## Expected Safe Behavior

- Extracted metrics are not dropped when backend transport fails.
- Flush failure pauses the harvest instead of pretending success.
- Retryable failures are retried within the flush cycle.
- Pending items remain available for a later manual flush.
- The popup should show backend recovery guidance, not navigation guidance, for backend flush failures.

## Verification Commands

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
npm --workspace @reup-douyin/extension-douyin-capture run test
```
