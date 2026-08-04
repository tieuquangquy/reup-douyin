# Bàn giao phiên đang dở — Phase 1 Random-5

**Ngày cập nhật:** 2026-07-26  
**Trạng thái:** claim v54/v55 trước đã bị hủy do lẫn source-text rồi sót ingredient labels; mixed v58/v55/v54 hiện là **candidate**, vẫn chờ operator sign-off.  
**Chi tiết:** [`handoff-phase1-random5.md`](./handoff-phase1-random5.md)

## Kết quả hiện tại

Output hiện dùng:

```text
apps/api/tmp_phase1_random5_final_v58/  # 750...
apps/api/tmp_phase1_random5_final_v55/  # 747...
apps/api/tmp_phase1_random5_final_v54/  # 760..., 754..., 763...
```

| Video | Frames | Tracks | Hardsub | Confirmed / uncertain | Scorer |
|---|---:|---:|---:|---:|---|
| `7472735913513078057` | 746 | 34 | 15 | 34 / 0 | PASS |
| `7604099786644380635` | 1,045 | 35 | 16 | 35 / 0 | PASS |
| `7543241784286465306` | 1,307 | 50 | 20 | 50 / 0 | PASS |
| `7503536530008722698` | 1,839 | 71 | 27 | 71 / 0 | PASS |
| `7632302211641623154` | 1,532 | 49 | 20 | 49 / 0 | PASS |

Tất cả đều có:

- `uncertain_tracks = 0`;
- không có dense hardsub span chưa được timeline giải thích;
- không có box cuối rộng ít nhất `1.8×` dense detector core;
- không duplicate, không thiếu crop/keyframe;
- đã xem overlay contact sheet và boundary `OUT/IN/IN/OUT`.

## Sửa provenance mới nhất

V54 không kiểm soát được khác biệt giữa chữ editor và chữ in sẵn trên cảnh: position lock + OCR ổn định không phải bằng chứng provenance. Ví dụ source thật đã lọt: chữ in trên bếp/thiết bị và hai highlight cảnh ở video `747...`; chữ hướng dẫn in trên bếp ở video `750...`.

Invariant mới: non-hardsub micro track đứng một mình chỉ được vào SSOT khi có bằng chứng layout editor độc lập (editor-card anchor hoặc peer gần, đồng thời gian). Nếu không, drop có audit `isolated_micro_source_text`. Không hardcode video/frame/text/box.

1. Raw detector coverage trước merge là X authority cuối cho dense hardsub.
2. Nếu box cuối rộng ít nhất `1.8×` median detector union trên đủ frame, chỉ X bị thu về detector core; Y vẫn lấy từ ink refinement.
3. Detector shadow đã bị `local_text_reject`, `low_ink` hoặc `not_overlay_geometry` chỉ được scorer bỏ qua khi có final hardsub thật đang active cùng Y band. Nếu không có final track, vẫn FAIL recall.

Bug thật đã sửa ở video `7472735913513078057`, span `196–219`:

```text
[438, 1001, 1414, 1051]
→ [812.85, 1001, 1113.15, 1051]
```

Audit tích lũy đã xem 239 retained tracks của mixed Random-5: contact sheet provenance v55 cho tập cũ và sequential frame-centric audit v58 cho hai label phục hồi; không chỉ kiểm tra đúng box operator chỉ ra.

Operator tiếp tục tìm thấy v55 bỏ `150g里脊肉`, `250g虾仁`, cắt trái `三个鸡蛋` và giữ một bottom shadow 2-hit. Root cause/fix v58:

- local OCR đọc đúng hai measurement label với confidence `0.996/0.992` nhưng gate chỉ cho phép `g` ở cuối chuỗi;
- cho phép measurement token nằm giữa amount và CJK ingredient name;
- measurement OCR variants của cùng label được hợp nhất có điều kiện, ingredient name khác vẫn tách;
- supported X-edge evidence lặp lại phục hồi glyph đầu, outlier đơn không được mở box;
- sparse two-hit hardsub shadow bị dense host purge;
- scorer FAIL mọi high-confidence multi-CJK `local_text_reject`.

QA boundary phải dùng sequential decode. OpenCV random seek trên clip này trả nội dung frame `N-1`.

## Tests đã chạy

```text
test_master_phase1_extractor.py: 79 PASS
test_phase1_text_gates.py: 38 PASS
test_phase1_score.py: 8 PASS
test_phase1_pass_contract.py: 44 PASS
test_phase1_*.py discovery: 98 PASS
```

## Việc còn mở

1. Operator xem/sign-off mixed output v55/v54; không dùng lại claim v54 5/5 cũ.
2. Không gọi đây là PASS chính thức trước sign-off.
3. Nếu operator chỉ ra lỗi mới: tiếp tục `FAIL → invariant → regression → rerun video bị ảnh hưởng`; không hardcode video/frame/text/box.

## Lệnh kiểm tra nhanh

```powershell
cd C:\Users\PC\Desktop\reup_douyin\apps\api
$env:PYTHONPATH='.'
python scripts/score_phase1_pass.py `
  tmp_phase1_random5_final_v55/7472735913513078057 `
  tmp_phase1_random5_final_v54/7604099786644380635 `
  tmp_phase1_random5_final_v54/7543241784286465306 `
  tmp_phase1_random5_final_v58/7503536530008722698 `
  tmp_phase1_random5_final_v54/7632302211641623154
```
