# Growth Score V1 + Affiliate Opportunity Ranking

## Mục tiêu

Growth Score V1 đánh giá tốc độ tăng trưởng của một `PlatformPublication` từ metric snapshots đã thu thập. Opportunity Ranking đặt Growth Score cạnh Affiliate Fit Score để operator xác định cơ hội pilot, nhưng không cộng hai điểm thành một điểm tổng và không tự thực hiện placement.

## Cổng an toàn

Một item chỉ xuất hiện trong Opportunity Ranking khi:

- `AffiliateProductMatch` hiện tại đã được `APPROVED` hoặc `OVERRIDDEN`;
- operator đã chọn một sản phẩm;
- publication, product match và product cùng workspace.

`PRIORITY` chỉ là khuyến nghị review. Nó không cấp quyền chèn link, comment, product tag hoặc publish.

## PublicationGrowthAssessment

Mỗi assessment lưu:

- `score_version = GROWTH_SCORE_V1`;
- fingerprint của toàn bộ metric evidence đầu vào;
- snapshot IDs và latest snapshot;
- Growth Score, breakdown và evidence;
- trạng thái, confidence và job tạo assessment;
- cờ `is_current` và metadata xác nhận `auto_placement = false`.

Khi có snapshot mới hoặc derivation thay đổi, fingerprint khác làm assessment hiện tại được đánh dấu stale trong Opportunity Ranking. Operator chạy lại score để tạo assessment mới; lịch sử cũ vẫn được giữ.

## Thành phần Growth Score

| Thành phần | Điểm tối đa |
|---|---:|
| View velocity | 35 |
| View acceleration | 25 |
| Engagement quality | 20 |
| Publication freshness | 10 |
| Data quality | 10 |

### View velocity

Điểm theo Views/hour ổn định:

- `>= 1000`: 35
- `>= 200`: 28
- `>= 50`: 20
- `>= 10`: 12
- `> 0`: 6
- `0`: 0

### View acceleration

So sánh velocity gần nhất với velocity ổn định trước đó:

- ratio `>= 1.50`: 25
- ratio `>= 1.15`: 20
- ratio `>= 0.90`: 14
- ratio `>= 0.50`: 7
- thấp hơn: 0

Khi chưa đủ lịch sử để tính acceleration, V1 dùng mức trung tính 10 điểm và hạ confidence.

### Engagement, freshness và chất lượng dữ liệu

Engagement ưu tiên `engagement_delta_rate_percent`, fallback sang cumulative engagement rate. Freshness dựa vào tuổi publication. Data quality phân biệt `COMPLETE`, `PARTIAL`, `UNKNOWN`, `SUSPECT` và giảm điểm cho estimated data.

## Trạng thái và confidence

- `INSUFFICIENT_DATA`: chưa có ít nhất hai snapshot cách nhau đủ 30 phút hoặc chưa có stable velocity.
- `COUNTER_REGRESSION`: platform counter giảm; không phát hành Growth Score.
- `STALE`: metric mới nhất cũ hơn 24 giờ.
- `READY`: đủ dữ liệu ổn định để chấm điểm.

Confidence:

- `HIGH`: tối thiểu ba snapshots, hai velocity ổn định, data `COMPLETE`, không estimated và measurement mới trong 6 giờ.
- `MEDIUM`: đủ stable velocity nhưng chưa đáp ứng toàn bộ điều kiện HIGH.
- `LOW`: dữ liệu thiếu, stale hoặc không ổn định.

## Ma trận Opportunity Ranking

Growth Score và Affiliate Fit Score luôn được giữ riêng:

| Growth | Affiliate Fit | Recommendation |
|---|---|---|
| `>= 70` | `>= 70` | `PRIORITY` |
| `>= 70` | `< 70` | `DO_NOT_PLACE` |
| `< 40` | `< 45` | `DO_NOT_PLACE` |
| Các trường hợp đủ dữ liệu khác |  | `MONITOR` |
| Thiếu/stale score hoặc thiếu Affiliate Fit |  | `INSUFFICIENT_DATA` |

Sản phẩm inactive hoặc out-of-stock luôn là `DO_NOT_PLACE`.

## Durable job

`CALCULATE_GROWTH_SCORE` gồm:

1. `validate_publication`
2. `load_metric_evidence`
3. `calculate_and_persist`
4. `finalize`

Worker kiểm tra fingerprint trước khi persist. Nếu metric thay đổi trong lúc job chạy, job fail với `growth_score_inputs_changed` để operator chạy lại trên evidence mới.

## API

- `GET /platform-publications/{id}/growth-score`
- `POST /platform-publications/{id}/growth-score-jobs`
- `GET /affiliate-opportunities/review-queue`

## UI

Tab **Opportunity Ranking** nằm trong Publication Library và hiển thị:

- Growth Score và confidence;
- Affiliate Fit Score riêng biệt;
- recommendation và lý do;
- trạng thái stale/insufficient;
- breakdown từng thành phần và evidence;
- nút calculate/recalculate durable job.

## Non-goals V1

- Không tạo combined score.
- Không tự động comment hoặc chèn affiliate link.
- Không tự động gắn product tag.
- Không publish.
- Chưa dùng conversion/commission outcome để huấn luyện hoặc điều chỉnh threshold.
