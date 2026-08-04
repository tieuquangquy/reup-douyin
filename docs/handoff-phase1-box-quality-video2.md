# Agent handoff — Phase 1 box quality (video 2)

> Dùng file này làm **context đầy đủ** khi mở chat/agent mới. Không cần đọc lại toàn bộ transcript cũ.

**Ngày:** 2026-07-25  
**Repo:** `reup_douyin`  
**Trạng thái:** File này giữ lịch sử video 2/v12. Các claim Random-5 v54/v55 đã bị hủy vì source-text và missing ingredient labels; mixed v58/v55/v54 hiện chỉ là **candidate**, vẫn chờ operator sign-off. Xem [`handoff-phase1-random5.md`](./handoff-phase1-random5.md).

---

## Cập nhật hiện tại — provenance/recall v58/v55/v54 (2026-07-26)

- Output video 2 hiện tại: `apps/api/tmp_phase1_random5_final_v54/7604099786644380635/`.
- Video 2: 1,045 frame, 35 track, 16 hardsub, 35 confirmed, 0 uncertain, scorer PASS.
- Cả manifest Random-5: mixed scorer 5/5 và đã audit 238 retained tracks; đây không phải operator PASS.
- Hai video lỗi provenance dùng v55 (`747...`, `750...`); video 2 `760...` không bị invariant mới tác động nên vẫn dùng output v54.
- Invariant provenance: non-hardsub micro không được vào SSOT chỉ nhờ screen lock/OCR; phải có editor-layout anchor/peer, nếu không audit `isolated_micro_source_text`.
- Invariant mới sau video 2: raw pre-merge detector coverage là X authority cuối cho dense hardsub; chặn box balloon `≥1.8×` detector core nhưng giữ ink-refined Y.
- Scorer phân biệt detector shadow đã bị strong gate loại với missing caption: chỉ miễn khi có final hardsub thật active cùng Y band.
- Regression hiện tại: 79 extractor + 38 text gate + 8 scorer + 44 PASS contract + 98 discovered Phase 1 tests đều PASS.
- Chi tiết, scoreboard và ca sửa mới: [`handoff-phase1-random5.md`](./handoff-phase1-random5.md).

Phần còn lại của file là lịch sử v12 để truy vết quyết định kỹ thuật.

---

## 1. Mục tiêu sản phẩm

- App local-first `reup-douyin`: hardsub / OCR / translate / cover / render.
- **Phase 1** = `MasterPhase1Extractor` → SSOT hình học text editor: `master_timeline.json`.
- Downstream (OCR, translate, cover, render) **chỉ** đọc timeline này — không re-scan full video theo authority cũ.
- Operator review bằng `qa/overlays/*.jpg` (**1 ảnh / 1 track**, không phải mọi box đồng thời trên 1 frame).

### Video đang làm

| | |
|--|--|
| Video id | `7604099786644380635` |
| File | `.douyin_profiles/download_staging/7604099786644380635.mp4` |
| Random-5 | `apps/api/tmp_phase1_random5/MANIFEST.json` |
| Video 1 | `7472735913513078057` — đã PASS sớm hơn; **không** hardcode geometry từ video đó |

### Output mới nhất

`apps/api/tmp_phase1_pass_v12_7604099786644380635/`

- `master_timeline.json`
- `text_frame_coverage.json` (pre-gate detect authority)
- `qa/overlays/`, `qa/boundaries/`, `qa/boundary_crops/`, `qa/summary.json`
- `crops/`, `frames/`

---

## 2. Luồng Phase 1 (chokepoint chính)

**File:** `apps/api/src/media_pipeline/frame_sampling/master_phase1_extractor.py`  
**Runner:** `apps/api/scripts/run_phase1_only.py`  
**Detector:** `local_text_detector.py` (DBNet)  
**Recognizer:** RapidOCR / `LocalTextRecognizer` (gate CJK)

Pipeline (tóm tắt):

1. Full-frame ROI (`ROI_Y0=0`, `ROI_Y1=1`); STEP=1; pad=STEP  
2. Coarse + dense rescan → `DetectionHit`  
3. `merge_tracks_by_centroid` (hardsub width/edge break; mid-overlay size class)  
4. `confirm_tracks` → `finalize_confirmed_tracks` (split / shrink / purge chrome)  
5. `filter_tracks_by_local_text` (OCR + geometry + scene vs editor)  
6. `coalesce_near_duplicate_tracks`  
7. `purge_redundant_hardsub_fragments`  
8. `split_tracks_by_local_text_change` (local OCR fingerprint/timing; Cloud OCR vẫn là content authority)  
9. `refine_track_boundaries_by_template`  
10. `extend_hardsub_tracks_to_ink` (extend + trim X/Y)  
11. Re-purge fragment, export timeline + QA overlays  

**Quy tắc repo bắt buộc:**

- `RULE.md` / diagnose-before-act / root-cause-first  
- **Test-first** cho bug hành vi: FAIL → fix → PASS  
- Sửa invariant cho mọi video; **cấm** hardcode video id / timestamp / geometry 1 clip  
- Windows; Python 3.11; `PYTHONPATH=apps/api` khi chạy test từ `apps/api/tests`

---

## 3. Diễn biến cuộc trò chuyện (tóm tắt)

### Trước handoff này (chat dài hơn)

Operator không follow hết tech Phase 1; từ test thực tế thấy:

- Miss text frames  
- Box không ôm sát glyph  

Đã làm (lũy kế): full ROI, nới recall, rồi siết FP (`low_ink`, tall flecks, purge fragment). Nhiều dir tạm `tmp_phase1_*_v2_*`. Từng claim “PASS candidate” ~24 tracks rồi **operator vẫn FAIL** bằng screenshot.

### Trong cuộc trò chuyện này

1. Operator gửi 3 ảnh: box sót / thiếu / không chuẩn.  
2. Agent chẩn đoán 3 root cause riêng → test-first → fix → re-run **v5**.  
3. Operator gửi thêm `sub_11`: box quá rộng trái (gỗ).  
4. Agent giải thích: detect đúng, **extend** balloon trái. Operator OK → fix → re-run **v6**.  
5. Operator xin file `.md` handoff; rồi xin bản **đủ để mang sang AI agent khác** (file này).

---

## 4. Bốn lớp lỗi đã xử lý

### A. Hardsub bị cắt trái (ví dụ: thiếu `这是一…`)

| | |
|--|--|
| **Symptom** | Box chỉ cover phần phải của dòng |
| **Evidence** | Extend có thể grow trái; trim/recover khóa lại seed hẹp; CJK gap ~60px không merge |
| **Root** | Recover early-exit với `seed_w≈0.25–0.35`; trim không absorb neighbor run |
| **Fix** | Recover chỉ stub `w<0.22` (hoặc widen thật); trim absorb **≤1** neighbor/side |
| **Tests** | `test_trim_completes_right_biased_*`, `test_extend_tracks_completes_right_biased_*` |

### B. Sót hardsub dòng kế (ví dụ: `一勺原味豆瓣酱` ~f348)

| | |
|--|--|
| **Symptom** | Overlay chỉ thấy note trên; timeline không có bottom hardsub trong khoảng ~325–368 |
| **Evidence** | `text_frame_coverage` **có** hardsub `[832,…,1147]` 328–366; merge/purge giữ được nếu replay riêng; SSOT mất track |
| **Root** | `purge_redundant_hardsub_fragments` xóa stub nằm trong X-span host rộng **không cần time-overlap** → nuốt dòng sau ngắn hơn |
| **Fix** | Stub-cover **bắt buộc** overlap thời gian với wide host |
| **Tests** | `test_purge_keeps_later_shorter_hardsub_without_time_overlap` |

### C. Sót title giữa khung (`懒人无米饭包`)

| | |
|--|--|
| **Symptom** | Chỉ còn chip calorie `379千卡` |
| **Evidence** | Detect title sớm `[596,493,1337,591]`; bị merge với rematch slab cao hơn → `scene_text` / split OCR rác; hoặc `oversized_blob` khi `h/fh≈0.09` |
| **Root** | Merge mid quá lỏng (height soft floor 0.25); oversized threshold 0.085; split làm hỏng title |
| **Fix** | `mid_title_ok` trong oversized; skip split cho mid title geom; height long-line ≥0.40; `_mid_overlay_geometry_compatible` (h≥0.55, w≥0.65) khi merge mid |
| **Tests** | `test_filter_keeps_wide_mid_title_line`, `test_mid_title_does_not_merge_with_*` |

### D. Box quá rộng trái trên dòng đã đủ (`sub_11`)

| | |
|--|--|
| **Symptom** | Pad trống lớn bên trái chữ `这样吃起来口感更丰富` |
| **Evidence** | Median detect `~[651,1016,1260,1053]` w≈0.32 tốt; sau extend → `x0=0`; SSOT cũ `x0≈231` |
| **Root** | `extend_hardsub_box_to_ink` walk trái bằng soft thr; gỗ/food blur **ink ≈ seed_mean** |
| **Fix** | Left-walk chỉ khi bridge ≥ `0.75 * seed_mean`; reject balloon mép frame / pad quá rộng trên seed `w≥0.28`; trim snap pad trái yếu/mép |
| **Result v6** | `sub_11` `x0=651` (đã hết pad trái lớn). **Right vẫn hơi rộng** (`x1≈1611`, w≈0.50) — follow-up có thể mirror guard bên phải |
| **Tests** | `HardsubInkExtendTests.test_extend_complete_mid_line_does_not_left_walk_into_wood` |

### E. Lớp boundary/geometry v10 (lịch sử ngay trước v12)

| | |
|--|--|
| **Boundary** | Temporal glyph-template verifier thay blind pad khi positive/background separable; 21/29 track đổi span có audit |
| **Recall** | Purge fragment cần substantial time-overlap, khôi phục câu thật `先给土豆切成细丝` frame `220–275` |
| **Geometry** | Neutral bright-glyph consensus ≥2 frame, fail-soft theo DBNet evidence |
| **Câu 272–324** | Từ box rộng `[98,…,1425]` → khoảng `[635,…,1251]`, visual ôm đủ glyph |
| **`sub_11` cũ** | Từ `[651,…,1611]` → khoảng `[689,…,1226]`, hết pad phải |
| **QA** | `quality_report.json`, `uncertain_candidates.json`, `boundary_evidence` |
| **Contract** | `docs/phase1-quality-contract.md` |

### F. Content-aware timing v12 (mới nhất)

| | |
|--|--|
| **Root cause** | Geometry-only tracking gộp nhiều câu liên tiếp ở cùng subtitle locus thành một timeline row; Phase 2 chỉ OCR một keyframe nên sẽ áp sai nội dung cho cả span |
| **Chokepoint** | Sau local-text gate/coalesce/purge, trước boundary và ink refinement |
| **Fix** | Batch `LocalTextRecognizer` trên từng frame; normalize CJK/digit signature; cluster ổn định; support ≥2; split theo content; rebuild hit box/keyframe trong từng segment |
| **Fail-soft** | OCR glitch một frame không tạo segment; cluster yếu/interleaved giữ track cũ; Cloud OCR không bị thay authority |
| **Track cũ 9–207** | Tách thành `11–74`, `79–149`, `154–205` tương ứng ba câu thật |
| **Các split khác** | `422–568`, `568–683`, `753–874`, `874–1001` đều tách thành hai câu |
| **Title** | Card đầu clip từ `0–6` được OCR timing siết đúng `0–3` |
| **Kết quả** | 29 track trước segmentation → 36 segment → purge overlap → 35 final track |
| **QA** | 35 overlay + 35 full-frame boundary strip + 35 zoomed boundary crop; 35 confirmed, 0 uncertain final track |
| **Visual agent audit** | 19 title/hardsub strip: start/end có chữ, outer neighbor không chữ, box không thấy clip/balloon; 16 box endcard được kiểm chung trên full-frame overlay |

---

## 5. Kiểm tra nhanh v6 (đã đo)

> Phần v6 dưới đây là lịch sử. Contract và kết quả mới: `docs/phase1-quality-contract.md` và output v12.

| Check | Kết quả |
|-------|---------|
| Title + calorie đầu clip | Có |
| Hardsub hoàn thiện trái (~f100) | `x0≈608`, w≈0.41 |
| Bottom hardsub ~f348 | Có (`sub_06` 326–368) |
| `sub_11` left | OK (`x0=651`) |
| `sub_11` right | Còn rộng — chưa PASS visual tuyệt đối |
| Toàn video | **Chưa** claim PASS |

Các hardsub khác từng/`v6` vẫn có case `x0` thấp / `w` lớn (ví dụ `sub_04` w≈0.69) — cần audit overlays, không giả định hết sạch.

---

## 6. Lệnh vận hành

### Re-run Phase 1

```powershell
cd c:\Users\PC\Desktop\reup_douyin\apps\api
$env:PYTHONPATH = "c:\Users\PC\Desktop\reup_douyin\apps\api"
py -3.11 scripts/run_phase1_only.py `
  "c:\Users\PC\Desktop\reup_douyin\.douyin_profiles\download_staging\7604099786644380635.mp4" `
  "c:\Users\PC\Desktop\reup_douyin\apps\api\tmp_phase1_pass_vN_7604099786644380635"
```

(~7–8 phút trên máy operator.)

### Tests

```powershell
cd c:\Users\PC\Desktop\reup_douyin\apps\api\tests
$env:PYTHONPATH = "c:\Users\PC\Desktop\reup_douyin\apps\api"
py -3.11 -m unittest discover -s . -p "test_phase1_*.py"
py -3.11 -m unittest discover -s . -p "test_master_phase1_extractor.py"
```

Lần mới nhất: **80** phase1 + **43** master + **23** downstream bridge/OCR/contract — OK; `score_phase1_pass.py` PASS v12 (0 duplicate overlap, đủ crop/keyframe).

---

## 7. Thỏa thuận làm việc với operator

- Tiếng Việt OK; trả lời ngắn, đúng trọng tâm.  
- “ok” / “OK” sau đề xuất = được implement.  
- Yes/no thuần: chỉ trả lời ngắn nếu họ hỏi kiểu đó.  
- Không commit git trừ khi được yêu cầu.  
- Optimize **mọi video**, không golden-path 1 clip.  
- `qa/overlays` = 1 JPG/track — giải thích rõ khi operator tưởng thiếu box vì UX overlay.

---

## 8. Việc nên làm tiếp (agent mới)

1. **Operator sign-off** toàn `tmp_phase1_pass_v12_…/qa/overlays/` và `qa/boundary_crops/`.  
2. Xác nhận các content split, đặc biệt ba câu `11–74`, `79–149`, `154–205`; title `0–3`; hai câu `220–269`, `274–322`.  
3. Dùng `qa/quality_report.json` + `qa/uncertain_candidates.json` cho audit; không âm thầm bỏ one-hit candidate.  
4. Chỉ đánh dấu PASS video 2 khi operator xác nhận.  
5. Sau PASS video 2: chuyển video tiếp trong `MANIFEST.json` random-5.  
6. Giữ test-first; cập nhật handoff nếu đổi contract.

---

## 9. File / hàm hay đụng

```
apps/api/src/media_pipeline/frame_sampling/master_phase1_extractor.py
  - merge_tracks_by_centroid / _mid_overlay_geometry_compatible / _box_height_compatible
  - purge_redundant_hardsub_fragments
  - filter_tracks_by_local_text (oversized / mid_title / split)
  - extend_hardsub_box_to_ink / trim_hardsub_box_to_ink / extend_hardsub_tracks_to_ink

apps/api/tests/test_phase1_pass_contract.py
apps/api/tests/test_phase1_text_gates.py
apps/api/tests/test_master_phase1_extractor.py  # HardsubInkExtendTests

apps/api/scripts/run_phase1_only.py
```

---

## 10. Prompt gợi ý dán vào agent mới

```
Đọc docs/handoff-phase1-box-quality-video2.md (hoặc file handoff này).

Tiếp tục Phase 1 video 2 (7604099786644380635), latest out tmp_phase1_pass_v12_*.
Tôn trọng RULE.md: root-cause + test-first + invariant (không hardcode clip).
Ưu tiên: (1) operator sign-off overlays/boundary crops v12, (2) xem quality report/uncertain candidates,
(3) không claim PASS đến khi operator OK.
```

---

*Bản rút gọn cạnh output:* `apps/api/tmp_phase1_pass_v6_7604099786644380635/HANDOFF_PHASE1_VIDEO2.md` (có thể lệch phiên bản — ưu tiên file `docs/` này).
