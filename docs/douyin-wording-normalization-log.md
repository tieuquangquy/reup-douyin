# Douyin Wording Normalization Log

## 2026-04-23

### Findings

- `/accounts/douyin` already follows the persistent-profile UI shape, but translation strings still mixed old session-centric wording with the new profile-centric model.
- English copy used both `browser connect`, `browser runtime`, `browser profile`, and `session` in places that describe the same primary flow.
- Vietnamese copy was inconsistent and often mixed English terms with Vietnamese phrases for the same concept.
- `/intake` used `live fetch`, `force live refresh`, `account`, and `connection` inconsistently.
- Some account table labels were hardcoded in English (`Browser`, `Manual`, raw enum-like health/status values).

### Canonical Decisions

- Primary model: one connected Douyin account is backed by one reusable local browser profile.
- Primary UI terms:
  - `Connected Douyin account` / `Tài khoản Douyin đã kết nối`
  - `Local browser profile` / `Hồ sơ trình duyệt cục bộ`
  - `Open profile` / `Mở hồ sơ`
  - `Reopen profile` / `Mở lại hồ sơ`
  - `Validate` / `Kiểm tra`
  - `Use in Intake` / `Dùng trong Intake`
  - `Reset runtime state` / `Đặt lại trạng thái runtime`
- Session-centric wording is allowed only in troubleshooting text when it describes transient runtime recovery.

### Files Touched

- Pending.

### Verification Notes

- Pending.

### Status

In progress.
