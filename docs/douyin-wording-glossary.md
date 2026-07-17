# Douyin Wording Glossary

## Canonical Mental Model

Each connected Douyin account is backed by a reusable local browser profile. The browser profile is the preferred local-development path for login, validation, and live fetch preparation. Manual session import remains a fallback.

| English term | Vietnamese term | Meaning | Use in |
| --- | --- | --- | --- |
| Connected Douyin account | Tài khoản Douyin đã kết nối | Saved account record used by intake/live fetch | Account list, Intake selector |
| Source account | Tài khoản nguồn | Account used to fetch source profiles | Architecture/docs when distinguishing source from publish accounts |
| Default account | Tài khoản mặc định | Account used when Intake has no explicit selection | Account table, Intake |
| Local browser profile | Hồ sơ trình duyệt cục bộ | Persistent browser `userDataDir` tied to one account | Primary Douyin account UI |
| Browser runtime | Runtime trình duyệt | Temporary running Playwright/Chrome state | Troubleshooting/recovery |
| Open profile | Mở hồ sơ | Open the saved local browser profile | Primary account action |
| Reopen profile | Mở lại hồ sơ | Reopen a saved profile that is not currently active | Primary account action |
| Validate | Kiểm tra | Check account readiness for live fetch | Account action |
| Revalidate | Kiểm tra lại | Queue or run another validation pass | Secondary/ops action |
| Use in Intake | Dùng trong Intake | Open Intake with this account selected | Account action |
| Live fetch | Lấy dữ liệu trực tiếp | Fetch source profile data from Douyin now | Intake |
| Existing data | Dữ liệu có sẵn | Use already-ingested data without live fetch | Intake |
| Reset runtime state | Đặt lại trạng thái runtime | Clear stuck transient browser runtime/session state | Recovery/troubleshooting |
| Troubleshooting | Khắc phục sự cố | Secondary recovery/debug section | Collapsed/secondary UI |
| Blocked response | Phản hồi bị chặn | Strong signal Douyin blocked the request/session | Health/troubleshooting |
| Stale | Cũ | Needs validation or runtime refresh | Health/status |

## Deprecated Primary Wording

Avoid these in primary UI:

- `browser connect session`
- `connect attempt`
- `retry connect`
- `force restart`
- `session capture`
- `account-backed session`

These terms may remain in troubleshooting docs or low-level diagnostics where they describe transient runtime behavior.
