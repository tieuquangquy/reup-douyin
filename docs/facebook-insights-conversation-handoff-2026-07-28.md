# Biên bản hội thoại và handoff Facebook Insights

Ngày cập nhật: `2026-07-28`  
Project: `reup_douyin`  
Runtime mục tiêu hiện tại: local-first trên Windows, giữ ranh giới SaaS-ready

## 1. Mục đích tài liệu

Tài liệu này lưu lại các yêu cầu, quyết định kỹ thuật, phần đã triển khai, kết quả kiểm
thử và việc cần làm tiếp theo trong nhánh công việc sau khi đã có video đầu ra hoàn chỉnh:

- xuất bản và quản lý nhiều tài khoản mạng xã hội;
- theo dõi hiệu suất publication/video;
- phân loại và chấm điểm tăng trưởng;
- chuẩn bị dữ liệu phục vụ affiliate/product matching;
- triển khai Facebook Reels Insights theo API chính thức và cơ chế fail-closed.

Đây là bản tóm tắt handoff, không phải transcript nguyên văn. Tài liệu không chứa access
token, cookie, mật khẩu hoặc secret thật.

## 2. Định hướng sản phẩm đã thống nhất

Luồng dài hạn cần kết nối thành chuỗi:

```text
Final video
  -> publish authority
  -> chọn đúng platform account
  -> publish/reconcile publication thật
  -> thu thập metrics theo cadence
  -> tính tăng trưởng và chấm điểm
  -> phân loại chủ đề/sản phẩm phù hợp
  -> đánh giá affiliate eligibility
  -> operator duyệt product tag hoặc affiliate comment
  -> theo dõi click/order/commission khi provider cho phép
```

Các nguyên tắc quan trọng:

- ưu tiên API chính thức và thao tác có sự đồng ý của operator;
- không xây cơ chế né antibot, giả fingerprint hoặc vượt bảo vệ tài khoản;
- account bị hold/cooldown/auth failure phải dừng an toàn;
- mọi tác vụ dài phải là durable job, có retry, idempotency, resume và error code;
- token chỉ được resolve trong worker và không được persist/log;
- scheduler không tự bật chỉ vì adapter đã tồn tại;
- native product tag, affiliate comment và auto-publish là các authority riêng, không gộp
  ngầm với metrics collection.

## 3. Nền tảng đã có trước Facebook live pilot

Các lớp authority và persistence liên quan đã có:

- `PlatformPublication` làm authority cho một publication bên ngoài;
- `PublicationMetricSnapshot` lưu số liệu quan sát theo thời gian;
- growth delta, view velocity, engagement và backfill recomputation;
- durable job `COLLECT_PUBLICATION_METRICS`;
- retry/backoff, metrics-only cooldown và resume từ snapshot đã commit;
- adaptive `PublicationMetricSchedule` với `ACTIVE`, `PAUSED`, `BLOCKED`, `COMPLETED`;
- scheduler worker sweep có feature flag và mặc định tắt;
- `LOCAL_MOCK` phục vụ regression, bị chặn trong production.

Migration head hiện tại:

```text
0036_metric_cadence (head)
```

## 4. Facebook Reels Insights Adapter V1 đã triển khai

Collector: `FACEBOOK_GRAPH`.

### 4.1. Network boundary

- endpoint dạng `/{media-id}/video_insights`;
- token nằm trong `Authorization: Bearer ...`, không nằm trong URL;
- media ID được URL-encode;
- metric name đi qua allowlist;
- Graph API version, object-ID source và watch-time unit được validate fail-closed;
- provider error summary chỉ giữ HTTP status và Graph code/subcode an toàn.

### 4.2. Chuẩn hóa metrics

Các trường V1 có thể ánh xạ:

- view count;
- total watch time, chuẩn hóa về giây;
- complete views và completion rate;
- like/reaction;
- comment;
- share;
- save;
- impression;
- reach.

Nếu provider không trả một metric:

- giữ giá trị `null`, không tự biến thành `0`;
- ghi tên metric vào `unavailable_metrics`;
- đánh dấu data quality là `PARTIAL` khi phù hợp.

Completion rate chỉ được tính khi có cả view count dương và complete-view count.

### 4.3. Error classification

- HTTP `429` hoặc Graph code `4`, `17`, `32`, `613`: rate limit, có retry;
- HTTP `401/403` hoặc Graph code `10`, `190`, `200`: auth/permission terminal;
- HTTP `404` hoặc Graph code `100`: media not found terminal;
- connection/5xx: bounded retry;
- invalid JSON/config/credentials/capability/preflight: terminal operator action.

### 4.4. Resume safety

Nếu snapshot đã commit nhưng worker crash trước khi finalize:

- lần chạy lại lấy snapshot đã có;
- không resolve token;
- không gọi provider lần hai;
- thay đổi hold/cooldown sau snapshot không làm mất khả năng finalize kết quả đã persist.

## 5. Fixture-only PostgreSQL pilot

Đã có runner:

```powershell
cd apps/api
python -m scripts.run_facebook_insights_fixture_pilot --publication-id <uuid>
```

Pilot dùng PostgreSQL và đường đi thật:

```text
enqueue -> JobRunner -> collector -> snapshot -> resume
```

Transport được inject bằng fixture in-memory, không có URL/socket implementation.

Kết quả regression gần nhất:

- publication: `31dc48a1-5de2-445a-84d9-71d4ce559e18`;
- account: `30f2b068-4247-40b1-acb6-122ba1c505f4`;
- job: `fd0c1488-28e6-40d0-b7f9-f32ff4761dfa`;
- snapshot: `02730405-0b36-4dfd-9537-b698bbbda0f5`;
- status: `COMPLETED`;
- provider call count: `1`;
- resume reuse snapshot: `true`;
- external network: `false`;
- dummy token persisted: `false`;
- view count fixture: `5100`;
- total watch time: `663` giây;
- completion rate: `65%`;
- data quality: `COMPLETE`.

Sau pilot, capability account được phục hồi về `false` và không có chuỗi dummy token
trong JSON persistence.

## 6. Controlled-live preflight đã triển khai

Endpoint:

```http
POST /platform-publications/{publication_id}/facebook-insights-live-preflight
```

Request yêu cầu operator xác nhận chính xác:

```json
{
  "operator_confirmation": "FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED",
  "expected_platform_account_id": "<account-uuid>",
  "expected_external_account_id": "<facebook-page-id>",
  "expected_media_id": "<facebook-reel-or-video-id>",
  "required_scopes": ["read_insights", "pages_read_engagement"]
}
```

Preflight là read-only:

- `network_used=false`;
- không resolve access token;
- không gọi Facebook;
- chỉ trả danh sách check và blocker code đã sanitize.

Guard này được enforce lại tại cả:

1. enqueue collection job;
2. worker execution ngay trước credential/provider boundary.

Do đó caller không thể bỏ qua preflight bằng endpoint collection cũ. Fixture pilot chỉ có
thể bypass bằng constructor flag nội bộ được inject rõ ràng; runtime bình thường mặc định
fail-closed.

## 7. Attestation bắt buộc trước live call

### PlatformAccount

Account phải là `FACEBOOK_REELS`, `ACTIVE`, không hold/cooldown và có:

```json
{
  "metrics_insights_enabled": true,
  "facebook_insights_token_type": "PAGE_ACCESS_TOKEN",
  "facebook_insights_verified_external_account_id": "<same-page-id>",
  "facebook_verified_insights_scopes": [
    "read_insights",
    "pages_read_engagement"
  ],
  "facebook_insights_scopes_verified_at": "<timezone-aware-ISO-datetime>",
  "graph_api_version": "<verified-vMajor.Minor>",
  "facebook_insights_object_id_source": "external_reel_id"
}
```

Ngoài metadata:

- `external_account_id` phải là Page ID thật;
- `token_reference` phải là tên biến môi trường viết hoa hợp lệ;
- token thật chỉ đặt trong local/server environment, không ghi vào DB hoặc tài liệu.

### PlatformPublication

Publication phải có:

- status `PUBLISHED`;
- Facebook Page/account authority khớp;
- external publish/media/reel ID thật;
- permalink thuộc `facebook.com` hoặc `fb.watch`;
- metadata:

```json
{
  "facebook_insights_verified_media_id": "<same-media-id>",
  "facebook_insights_object_verified_at": "<timezone-aware-ISO-datetime>"
}
```

Scope và media verification phải không cũ hơn 30 ngày tại thời điểm one-shot pilot.

## 8. Trạng thái live hiện tại

Preflight trên dữ liệu local hiện tại trả:

```text
ready_for_live_job=false
network_used=false
```

Nguyên nhân:

- Page/account ID là demo;
- publication/media ID là local placeholder;
- permalink là `example.invalid`;
- token reference hiện tại chưa đạt contract live và token environment chưa sẵn sàng;
- chưa attestation `PAGE_ACCESS_TOKEN`;
- chưa xác minh `read_insights` và `pages_read_engagement`;
- chưa có account binding và media binding;
- capability insights đang tắt.

Không có Facebook live request nào được thực hiện. Scheduler vẫn tắt.

## 9. Việc operator cần cung cấp tiếp theo

Không gửi token qua chat. Cần chuẩn bị các giá trị không bí mật:

```text
Page ID thật:
Reel/video object ID thật:
Permalink Facebook:
Tên biến môi trường chứa token:
Graph API version đã xác minh:
Scopes đã xác minh:
```

Đặt token cục bộ, ví dụ trong `apps/api/.env`:

```env
FACEBOOK_PAGE_MAIN_INSIGHTS_TOKEN=<real-page-access-token>
```

File `.env` không được commit.

## 10. Trình tự tiếp tục được khuyến nghị

1. Tạo/cập nhật một `PlatformAccount` thật.
2. Tạo/cập nhật đúng một `PlatformPublication` thật thuộc account đó.
3. Ghi account/media attestation sau khi operator kiểm tra trên Meta.
4. Chạy controlled-live preflight.
5. Chỉ khi `ready_for_live_job=true`, enqueue đúng một `FACEBOOK_GRAPH` job.
6. Giữ scheduler tắt và quan sát job/snapshot/provider code.
7. Kiểm tra lại token leakage, idempotency và resume.
8. Operator duyệt kết quả canary.
9. Sau đó mới thiết kế recurring authorization và bật adaptive cadence có kiểm soát.

## 11. Bằng chứng kiểm thử gần nhất

- `75` test liên quan metrics, Facebook, JobRunner và worker runtime: PASS;
- mapper/OpenAPI: PASS;
- số OpenAPI paths: `216`;
- Alembic: `0036_metric_cadence (head)`;
- `git diff --check`: không có whitespace error, chỉ có cảnh báo line-ending Windows;
- dummy token match trong persisted JSON: `0`.

## 12. File quan trọng

- `apps/api/src/analytics/collectors/facebook_reels_insights.py`
- `apps/api/src/analytics/services/facebook_insights_live_pilot_service.py`
- `apps/api/src/analytics/services/publication_metric_collection_service.py`
- `apps/api/src/analytics/services/publication_metric_cadence_service.py`
- `apps/api/src/analytics/services/publication_metric_retry_policy.py`
- `apps/api/src/api/routes/analytics.py`
- `apps/api/src/schemas/analytics.py`
- `apps/api/scripts/run_facebook_insights_fixture_pilot.py`
- `apps/api/tests/test_facebook_reels_insights_collector.py`
- `apps/api/tests/test_facebook_insights_live_pilot_preflight.py`
- `docs/facebook-reels-insights-adapter-v1.md`
- `docs/publication-metrics-collector-v1.md`
- `docs/publication-metrics-cadence-v1.md`

## 13. Phạm vi chưa triển khai trong bước này

- không gọi Facebook live;
- không tự bật scheduler;
- không tự tạo hoặc gia hạn Meta token;
- không triển khai TikTok/YouTube insights adapter;
- không tự đăng affiliate comment;
- không tự gắn native product tag;
- chưa triển khai click/order/commission attribution;
- chưa dùng metrics để tự động quyết định affiliate eligibility.

Các phần trên cần được triển khai thành các authority/job riêng sau khi Facebook insights
canary thật đã PASS.
