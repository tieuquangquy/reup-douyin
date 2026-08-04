# Affiliate Catalog + Product Matching V1

## Product image upload

The Affiliate Catalog editor accepts either a public image URL or an upload from the operator computer.

- Supported input formats: JPEG, PNG, and WebP.
- Maximum source size: 8 MB.
- The API verifies image bytes, applies EXIF orientation, strips metadata, converts to RGB JPEG, and resizes images larger than 4096px on either axis.
- Files are stored through the local storage abstraction and deduplicated by SHA-256 within the workspace.
- The API returns an immutable UUID URL at `/api/public/affiliate-product-images/{asset_id}`. The public route is tokenless so Meta can fetch the attachment and serves only sanitized JPEG bytes.

When the app runs on localhost, the uploaded image is available for catalog preview. Facebook comment preview remains fail-closed until that URL is reachable over public HTTPS. Configure the fixed Cloudflare tunnel as the Facebook OAuth redirect origin so new uploads automatically receive the tunnel URL. Ephemeral `*.trycloudflare.com` Quick Tunnel hosts are deliberately not treated as stable configured origins; the operator UI renders app-owned assets through its current `/api` origin so an expired tunnel cannot break local previews. After changing an image, save the product and regenerate the comment preview to capture the new attachment URL.

## Mục tiêu

V1 tạo một lớp kiểm duyệt sản phẩm liên kết giữa `PlatformPublication` và catalog sản phẩm. Hệ thống chỉ đề xuất sản phẩm có liên quan đến topic đã được duyệt, hiển thị điểm `Affiliate Fit Score` riêng với `Growth Score`, rồi chờ operator quyết định.

V1 không tự chèn link, không tự gắn product tag, không tự thả comment và không tự publish.

## Điều kiện đầu vào

Một publication chỉ được đưa vào matching khi classification hiện tại có:

- `decision_status = APPROVED` hoặc `OVERRIDDEN`;
- `primary_topic_id` hoặc topic phụ đã được lưu;
- cùng workspace với catalog và platform account.

Nếu chưa duyệt classification, API trả lỗi `affiliate_classification_not_approved`. Đây là cổng an toàn để không match sản phẩm dựa trên topic chưa được operator xác nhận.

## Luồng operator

1. Mở **Publishing settings → Affiliate Catalog**.
2. Thêm sản phẩm thủ công hoặc nhập CSV. Gắn một hoặc nhiều topic taxonomy cho sản phẩm.
3. Mở **Publishing → Publications → Product Matching**.
4. Chọn **Match** trên publication đủ điều kiện. API tạo durable job `MATCH_AFFILIATE_PRODUCTS`; worker xử lý nền và có thể resume/retry theo job policy.
5. Mở **Review** để xem các đề xuất, bằng chứng và breakdown điểm.
6. Chọn **Approve**, **Reject**, hoặc **Override**. Override bắt buộc chọn sản phẩm trong catalog và nhập lý do.

Quyết định được lưu trên `AffiliateProductMatch`, có operator, thời điểm và lý do. Một catalog hoặc classification thay đổi sẽ tạo fingerprint khác; operator cần chạy matching lại để có kết quả mới.

## Catalog

Mỗi sản phẩm thuộc một workspace và có fingerprint ổn định theo:

```text
PLATFORM:(external_product_id hoặc affiliate_url)
```

Sản phẩm `is_active = false` hoặc `availability_status = OUT_OF_STOCK` không được đưa vào candidate set. Catalog fingerprint chỉ bao gồm sản phẩm active, còn hàng, đúng `catalog_version`.

CSV tối thiểu dùng các cột sau:

```csv
platform,external_product_id,merchant_name,name,description,image_url,product_url,affiliate_url,currency_code,price_amount,commission_rate_percent,commission_amount,availability_status,keywords,supported_platforms,topic_codes,is_active
SHOPEE,SKU-001,Merchant,"Trà thảo mộc","Mô tả có, dấu phẩy",,,https://example.com/a,VND,99000,20,,IN_STOCK,"trà thảo mộc|giải khát","FACEBOOK_REELS|TIKTOK_SHOP",FOOD_DRINK,true
```

Các ô CSV được quote theo chuẩn RFC 4180; `keywords`, `supported_platforms` và `topic_codes` dùng dấu `|`. Topic code không tồn tại hoặc không active sẽ làm request bị từ chối thay vì âm thầm bỏ mapping.

`image_url` có thể được tạo, import CSV và chỉnh sửa trên giao diện Affiliate Catalog. Ảnh dùng cho Facebook affiliate comment phải là URL HTTPS công khai để Meta có thể tải; localhost, file local và địa chỉ mạng riêng không hợp lệ. Thay đổi ảnh làm catalog fingerprint thay đổi và chỉ áp dụng vào comment preview revision được tạo lại sau thay đổi.

## Affiliate Fit Score V1

Điểm tối đa 100 và không chứa dữ liệu tăng trưởng:

| Thành phần | Tối đa |
|---|---:|
| Topic relevance | 40 |
| Keyword/entity match | 25 |
| Availability | 15 |
| Commission quality | 10 |
| Platform compatibility | 10 |

Sản phẩm không có topic match và cũng không có keyword/entity match bị loại hoàn toàn, dù hoa hồng cao. Đây là nguyên tắc chống đề xuất sản phẩm không liên quan.

## Durable job

`MATCH_AFFILIATE_PRODUCTS` có bốn step:

1. `validate_classification`
2. `load_catalog`
3. `match_and_persist`
4. `finalize`

Payload lưu publication, classification, matcher version, catalog version, catalog fingerprint và số lượng suggestion. Worker kiểm tra lại classification/catalog fingerprint trước khi persist; nếu dữ liệu thay đổi, job fail với hướng dẫn chạy lại, không ghi kết quả cũ.

## API chính

- `GET/POST /affiliate-products`
- `PATCH /affiliate-products/{product_id}`
- `POST /affiliate-products/bulk-import`
- `GET /affiliate-product-matches/review-queue`
- `GET /platform-publications/{id}/affiliate-product-match`
- `POST /platform-publications/{id}/affiliate-product-match-jobs`
- `POST /affiliate-product-matches/{id}/decision`

Các endpoint yêu cầu authenticated operator session và luôn giới hạn theo `workspace_id`.

## Phạm vi chưa làm trong V1

- Không tự động chèn affiliate URL vào caption/comment.
- Không tự động gắn sản phẩm native cho TikTok Shop, Facebook hoặc Instagram.
- Không tự publish.
- Chưa dùng AI để match sản phẩm; matcher hiện tại deterministic để dễ kiểm toán.
- Chưa đồng bộ conversion/commission thực tế. Đây là đầu vào cho bước Affiliate conversion sync và `OUTCOME_SCORE_V2` sau khi review queue ổn định.

## Kiểm tra vận hành

Trước pilot:

```powershell
cd apps/api
alembic current
python -m pytest tests/test_affiliate_product_matching_v1.py -q
```

Sau khi cập nhật code worker, phải restart hai worker children để process nhận `MATCH_AFFILIATE_PRODUCTS`. Khi smoke test, dùng một sản phẩm catalog thật đã gắn topic và xóa/đánh dấu dữ liệu thử nghiệm sau khi xác nhận job completed, suggestion và decision endpoint.
