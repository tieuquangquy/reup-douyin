# Douyin Wording Style Guide

## Primary UI

Use product-language wording, not implementation-language wording.

Preferred:

- `Local browser profile`
- `Open profile`
- `Validate`
- `Use in Intake`
- `Reset runtime state`

Avoid in primary UI:

- `connect session`
- `capture session`
- `force restart`
- `active session exists`

## Troubleshooting UI

Troubleshooting can mention runtime/session details when needed, but should still explain what the operator can do next.

Examples:

- `Runtime state is stuck. Reset runtime state, then reopen the profile.`
- `Validation was inconclusive. Retry validation before reconnecting.`

## Vietnamese Parity

Keep the same concept mapping:

- `browser profile` = `hồ sơ trình duyệt`
- `browser runtime` = `runtime trình duyệt`
- `connected account` = `tài khoản đã kết nối`
- `live fetch` = `lấy dữ liệu trực tiếp`
- `validate` = `kiểm tra`

Do not alternate between `phiên`, `kết nối`, and `profile` for the same primary concept.

## Intentionally Left Unchanged

- Internal API error codes remain English and snake_case.
- Backend enum values such as `ACTIVE`, `STALE`, `BLOCKED` remain stable contracts.
- Low-level troubleshooting may still expose raw error codes for debugging.
