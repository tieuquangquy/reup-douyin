# Soft reconstruction cover v1

## Mục tiêu

Cơ chế này thay thế việc đổi qua lại nhiều kiểu xóa/làm mờ theo từng track bằng
một authority thống nhất cho mọi `EDITOR_OVERLAY_TEXT`. Mục tiêu là che kín chữ
nguồn nhưng giữ khối che ổn định, mềm, ít lộ biên và không nhấp nháy khi nội
dung hoặc cảnh chuyển động.

`SOURCE_INTRINSIC` tiếp tục được giữ nguyên pixel. Track `UNCERTAIN` không tự
động được dịch hoặc che. Cơ chế chạy hoàn toàn local; OCR residual QA cũng dùng
provider local.

## Runtime contract

- Render policy: `phase4_role_policy_v20_soft_reconstruction_epochs`.
- Cover policy: `editor_overlay_soft_reconstruction_v6`.
- Cover strategy: `soft_reconstruction_plate_v1`.
- Epoch schema: `soft_cover_epoch_v1`.
- Runtime có thể nâng cấp contract Phase 4 cũ trong bộ nhớ; không ghi đè
  `master_timeline.json`, `phase2_ocr_timeline.json` hoặc contract lịch sử.

Các track liên quan được gom vào một `soft_cover_epoch`. Epoch khóa:

- chiều cao glyph chuẩn;
- profile blur/feather/tint;
- kiểu mask bo mềm;
- thứ tự tái tạo;
- danh sách thành viên và khoảng thời gian.

Caption cùng lane có thể dùng chung epoch nhưng vẫn giữ ROI riêng đã được phê
duyệt; một caption ngắn không bị kéo thành khối che toàn màn hình.

## Thứ tự tái tạo

1. `temporal_clean_reference`: dùng clean plate đã căn chỉnh bằng ECC/optical
   flow khi evidence đủ tốt.
2. `spatial_surface_reconstruction`: chỉ dùng cho UI phẳng, không dùng cho
   caption hoặc vùng có protected-source carve-out.
3. `stable_soft_blur`: fallback an toàn, dùng Gaussian blur theo chiều cao chữ,
   tint từ nền lân cận, mask bo góc và feather hướng vào trong.

Nếu clean plate mất alignment, epoch khóa sang fallback ổn định cho phần thời
gian còn lại. Không được bật/tắt clean plate theo từng frame vì gây pulse/flicker.
Lịch sử aesthetic của epoch cũng được reset sau một khoảng frame không hoạt
động để không so sánh hai cảnh không liên tiếp.

## QA fail-closed

Render ghi các metric theo track:

- `boundary_seam_score`;
- `temporal_flicker_score`;
- `plate_uniformity_score`;
- `background_color_drift`;
- residual stroke energy và strong-stroke fraction.

Strong-stroke fraction phân biệt glyph còn đọc được với một ít texture cô lập
sau blur. Full-timeline QA vẫn quét mọi frame để phát hiện:

- frame không được edit;
- residual stroke;
- hư hại vùng `SOURCE_INTRINSIC`;
- flicker vượt ngưỡng;
- residual CJK bằng OCR local.

Không tăng ngưỡng flicker để lấy PASS. Nếu temporal reference gây mode-flapping,
runtime phải chuyển sang fallback ổn định.

## Visual smoke 2026-08-12

Fixture: `7429689966633979175`, 708 frame, 26.77 giây, 17 render tracks.

- Render: 83.940 giây, `h264_nvenc`, không encoder fallback.
- Full-timeline: PASS; 0 missing edit, 0 residual stroke, 0 protected-source
  damage.
- Flicker: `1.9603`, thấp hơn limit `12.0`.
- Local residual OCR: complete, 0 residual CJK.
- Output QA: PASS.

Artifact kiểm chứng:

- Video SHA-256:
  `f4dd3cfb046bbb8f9e5d58d28532265a7af08a17dda2e4347dfd751bc4dd1106`.
- Render QA SHA-256:
  `4973de3beda00687f776339a0ee9c9dcda3de5b2ab1b33b926842b6e0b2e7bb3`.
- Output QA SHA-256:
  `4f43918b62e2fb953f05326cfab589c529fbb33f8aaae833c3788fd17ddba14b`.

Đây là bằng chứng smoke cho một fixture, không phải tuyên bố hỗ trợ mọi video.

