# Facebook Affiliate Comment Connector V1

## Reusable comment templates

Publishing Settings now provides versioned Facebook Reel affiliate comment templates. A template owns the message format and default CTA/disclosure, while the selected catalog product supplies `product_name`, `description`, and the locked `affiliate_url`.

Supported variables are:

```text
{{cta}} {{product_name}} {{description}} {{affiliate_url}}
{{disclosure}} {{page_name}} {{reel_title}} {{topic_name}} {{product_image}}
```

`{{product_image}}` is an attachment control, not literal text. The template's **Attach product image automatically** setting resolves the catalog image to Facebook `attachment_url`. The image must still be a public HTTPS URL; localhost and private-network URLs fail closed.

`{{disclosure}}` is optional at the template-rendering layer. If an operator removes it, the renderer does not add disclosure text elsewhere or restore the variable. **Save** creates a new inactive version; **Save & Activate** creates and activates the new version in one explicit action. The Settings UI selects the newly created version so a later **Activate** action cannot accidentally reactivate the old version.

Templates are workspace-scoped, versioned, and activated one at a time for Facebook Reels. A placement stores the template id/version, rendered message, CTA/disclosure, and attachment snapshot. Editing or activating a newer template never changes an existing DRAFT, QUEUED, POSTING, or POSTED placement; use **Edit preview → Save & regenerate** to create a new audited revision.

Each opportunity has two explicit comment sources: **Shared template** and **Custom item comment**. Shared mode exposes every saved version and defaults to the active template. **Apply & regenerate** applies the selected saved version only to that Reel and creates a new immutable placement revision; it never modifies the shared template. An inactive version is labeled **Test only**: it may create an immutable preview for inspection, but the API refuses to approve that placement. Placement metadata records `comment_source` and whether a shared template was active at preview time so this rule cannot be bypassed through a direct API call.

Custom mode accepts arbitrary text plus the same supported `{{...}}` variables as a shared template. **Apply & regenerate** resolves those variables using the current Page, Reel, approved product, and catalog data. The Affiliate URL and product image are shown separately: `{{affiliate_url}}` is optional and chooses the link position; when omitted, the renderer appends the locked conversion link automatically. `{{product_image}}` controls the separate Facebook image attachment and never renders as literal text. Unsupported variables fail closed. The custom recipe and whether the URL was auto-appended are stored in placement metadata and never modify a shared template.

Before **Approve & post**, the UI shows a posting-readiness panel for the template policy, public HTTPS affiliate URL, unresolved placeholders, image policy, and current opportunity gates. The server independently validates the public URL and all publication/account/product/growth gates again. A template with image attachment enabled requires an image in the placement snapshot; a deliberate text-only comment must use a template version with image attachment disabled.

Inactive, unreferenced template versions may be deleted from Settings after operator confirmation. The active version must first be replaced, and any version referenced by a placement is retained for audit and cannot be deleted.

## Image attachment safety

An approved comment may include the selected catalog product image. The preview stores the exact `attachment_image_url` used by the worker, and the Facebook connector sends it as `attachment_url`. Only public HTTPS URLs are accepted at this boundary; localhost, private-network, file, and data URLs are rejected so a comment cannot be queued with an image Facebook cannot fetch.

For images uploaded in Affiliate Catalog, configure a fixed public HTTPS tunnel and save the product before creating or regenerating the preview. The upload endpoint normalizes JPEG/PNG/WebP input (8 MB maximum) into sanitized JPEG bytes at an immutable UUID path. Changing the catalog image never mutates an existing placement revision; regenerate a `DRAFT` or `FAILED` preview to record the new attachment.

## Mục tiêu

Connector V1 chuyển một Opportunity Ranking `PRIORITY` thành Facebook Reel comment theo luồng bắt buộc:

```text
Preview → Operator confirmation → Durable job → Facebook Graph API → Persist result
```

Không có bulk action và không có automatic placement trong V1.

## Điều kiện tạo preview

Server kiểm tra lại toàn bộ gate, không tin dữ liệu UI:

- publication là `FACEBOOK_REELS` và có external Reel id;
- product match hiện tại đã `APPROVED` hoặc `OVERRIDDEN`;
- sản phẩm được chọn active và không out-of-stock;
- Growth Score hiện tại là `READY`, không stale và fingerprint khớp metric snapshots;
- Growth Score và Affiliate Fit tạo recommendation `PRIORITY`;
- Facebook Page active, không hold/cooldown;
- OAuth capability đã verify `pages_manage_posts` và Page task `CREATE_CONTENT`.

Nếu bất kỳ gate nào thay đổi giữa preview và approval, approval bị chặn và operator phải tạo preview mới.

## Nội dung comment

Operator chỉnh CTA và disclosure trước khi tạo preview. Server ghép message cuối cùng theo thứ tự:

```text
CTA
Product name
Affiliate URL

Affiliate disclosure
```

Affiliate URL và disclosure được lưu trong preview. UI hiển thị message cuối read-only trước khi operator tick checkbox xác nhận và bấm **Approve & post**.

Nếu sản phẩm có `image_url`, server chụp URL ảnh vào `attachment_image_url` của placement revision. URL phải là HTTPS công khai, không phải localhost, mạng riêng hoặc file local. Preview hiển thị đúng ảnh sẽ gửi và connector truyền ảnh bằng `attachment_url` khi gọi Facebook comments API. Placement không có ảnh vẫn có thể đăng comment dạng text.

## Chỉnh sửa preview

Preview ở trạng thái `DRAFT` hoặc `FAILED` có nút **Sửa preview**. CTA và disclosure được mở lại để chỉnh sửa; affiliate URL vẫn lấy từ sản phẩm đã chọn và chỉ có thể thay đổi trong Affiliate Catalog hoặc bằng cách chọn product match khác.

Ảnh cũng lấy từ Affiliate Catalog. Sau khi sửa ảnh sản phẩm, operator phải **Sửa preview → Lưu & tạo lại preview** để revision mới chụp URL ảnh mới. Worker luôn dùng ảnh đã khóa trong revision được duyệt, không đọc lại ảnh có thể đã đổi trong catalog.

Khi operator bấm **Lưu & tạo lại preview**, server không sửa nội dung của revision cũ. Server tạo một placement revision bất biến mới, chuyển revision cũ thành không còn hiện hành và lưu `replaces_placement_id`/`superseded_by_placement_id` cho audit. Request lặp lại sử dụng idempotency key gắn với placement bị thay thế nên không tạo nhiều revision ngoài ý muốn.

Các trạng thái `QUEUED`, `POSTING` và `POSTED` luôn khóa chỉnh sửa để nội dung operator đã duyệt không khác nội dung worker gửi lên Facebook.

## Đăng comment tiếp theo

Sau khi placement hiện hành đạt `POSTED`, operator có thể chọn **Tạo comment tiếp theo**. Hệ thống tạo một placement sequence mới và chuyển comment đã đăng thành lịch sử; không sửa hoặc đăng lại placement cũ. Comment mới vẫn đi qua Preview, readiness và xác nhận thủ công riêng.

Policy an toàn cho cùng một Reel:

- nội dung mới không được trùng SHA-256 với bất kỳ comment đã đăng trước đó;
- tối đa 2 comment affiliate trong 24 giờ;
- cooldown 6 giờ giữa hai lần đăng;
- operator có thể chuẩn bị draft trong cooldown, nhưng approval bị khóa đến `next_allowed_at`;
- metadata lưu `placement_sequence` và `previous_posted_placement_id` để audit;
- lịch sử hiển thị message, thời gian, source và permalink của từng comment đã đăng.

## Trạng thái

- `DRAFT`: preview đã tạo, chưa gửi Facebook.
- `QUEUED`: operator đã approve và durable job đã tạo.
- `POSTING`: worker đang gọi Facebook.
- `POSTED`: Facebook trả external comment id.
- `FAILED`: connector hoặc gate thất bại.
- `CANCELLED`: dành cho cancellation workflow sau này.
- `BLOCKED`: dành cho policy enforcement sau này.

`PlatformPublication.affiliate_comment_status` được đồng bộ ở các bước `DRAFT`, `QUEUED`, `POSTING`, `POSTED`, `FAILED`.

## Idempotency và retry

Preview idempotency gồm:

```text
publication id + product match id + SHA-256(final message) + SHA-256(attachment image URL)
```

Post job idempotency gồm:

```text
placement id + message SHA-256
```

Một Reel chỉ có một placement hiện hành ở trạng thái `DRAFT`, `QUEUED`, `POSTING` hoặc `POSTED`. Reel có thể có nhiều placement `POSTED` trong lịch sử theo sequence, nhưng policy cooldown/quota/chống trùng luôn được kiểm tra lại ở approval.

Khi operator bấm lại lúc job hiện hành còn `QUEUED`, `RUNNING` hoặc `RETRYABLE`, hệ thống tái sử dụng job đó. Nếu job trước đã ở trạng thái kết thúc, hệ thống mới tạo một retry idempotency key riêng. Cơ chế này ngăn nhiều lần bấm tạo các job đăng comment trùng nhau.

## Durable job

`POST_AFFILIATE_COMMENT` gồm:

1. `validate_approval`
2. `resolve_page_credential`
3. `post_comment`
4. `persist_result`
5. `finalize`

Chỉ step `post_comment` gọi mạng. Worker kiểm tra lại gate trước khi gọi Graph API.

## Facebook boundary

Connector gọi:

```text
POST /{external_reel_id}/comments
```

Payload có `message` và, khi placement có ảnh, `attachment_url`.

Page token nằm trong HTTP `Authorization: Bearer ...`; không đưa token vào query string, response, logs hoặc public API. Token được resolve server-side từ encrypted platform credential.

Các lỗi rate limit, token hoặc permission được chuẩn hóa. Rate limit áp dụng cooldown; token/permission rejection có thể đặt Page vào safety hold theo policy hiện tại.

## API

- `GET /platform-publications/{id}/affiliate-comment-placement`
- `GET /platform-publications/{id}/affiliate-comment-placements`
- `POST /platform-publications/{id}/affiliate-comment-placement/preview`
- `POST /affiliate-comment-placements/{id}/approve`
- `POST /affiliate-comment-placements/{id}/verification-jobs` với body `{"authorize_network": true}`

## UI

Trong **Opportunity Ranking**:

1. Mở một item `PRIORITY`.
2. Chọn **Prepare comment**.
3. Chỉnh CTA/disclosure và tạo preview.
4. Kiểm tra Page, Reel, product, URL và gate snapshot.
5. Tick xác nhận.
6. Bấm **Approve & post**.
7. UI poll trạng thái `QUEUED/POSTING` cho đến `POSTED/FAILED`.
8. Sau `POSTED`, xem **Lịch sử comment đã đăng** hoặc chuẩn bị comment sequence tiếp theo theo policy an toàn.

## Xác minh sau khi đăng

Sau khi Facebook trả về comment id, hệ thống tự tạo durable verification job ở T+1 phút, T+15 phút và T+6 giờ. Operator cũng có thể bấm **Check now** trong lịch sử comment; các lần bấm lặp khi job đang chạy sẽ tái sử dụng job hiện tại.

Verification chỉ thực hiện thao tác đọc:

- xác minh comment còn tồn tại, không bị ẩn và nội dung không thay đổi;
- xác minh trạng thái ảnh đính kèm khi placement yêu cầu ảnh;
- kiểm tra affiliate URL qua từng redirect HTTPS công khai, chặn localhost/private IP và giới hạn số redirect;
- phân biệt link hỏng với trường hợp sàn thương mại điện tử chặn bot (`403 = ACCESS_RESTRICTED`);
- lưu kết quả đã rút gọn vào metadata placement để UI hiển thị màu.

Kết quả `HIDDEN`, `NOT_FOUND`, `CONTENT_MISMATCH`, `BROKEN` hoặc `UNSAFE_REDIRECT` chỉ tạo cảnh báo **Needs attention**. Hệ thống không tự sửa, xóa hay đăng lại comment.

## Non-goals V1

- Không tự động chọn item và post.
- Không bulk placement.
- Chưa đồng bộ click, conversion hoặc commission.
