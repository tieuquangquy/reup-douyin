# Phase 1 Random-5 — quality handoff

**Ngày:** 2026-07-26  
**Output:** mixed v58 (`750...`) + v55 (`747...`) + v54 (ba video còn lại)  
**Trạng thái:** các claim v54/v55 cũ đã bị hủy vì source-text và missing ingredient labels; output hiện là **candidate**, chưa phải operator PASS.

## Mục tiêu và cách làm

Random-5 được dùng để tìm invariant áp dụng cho mọi video:

```text
Random-5 → audit → FAIL → sửa invariant → regression → rerun
```

Không hardcode video id, frame, text hoặc box. `master_timeline.json` vẫn là geometry SSOT; local OCR chỉ là timing/fingerprint và false-positive evidence.

## Scoreboard

| Video | Frames | Frames có pre-gate hit | Tracks | Hardsub | Confirmed / uncertain | Scorer |
|---|---:|---:|---:|---:|---:|---|
| `7472735913513078057` | 746 | 746 | 34 | 15 | 34 / 0 | PASS |
| `7604099786644380635` | 1,045 | 1,041 | 35 | 16 | 35 / 0 | PASS |
| `7543241784286465306` | 1,307 | 1,303 | 50 | 20 | 50 / 0 | PASS |
| `7503536530008722698` | 1,839 | 1,835 | 71 | 27 | 71 / 0 | PASS |
| `7632302211641623154` | 1,532 | 1,531 | 49 | 20 | 49 / 0 | PASS |

Mọi output đều đạt contract tự động:

- quality report và text-frame coverage tồn tại;
- `uncertain_tracks = 0`;
- không dense uncovered hardsub span;
- không final hardsub `≥1.8×` dense detector core;
- không duplicate pair, empty-left wide hardsub hoặc thiếu crop/keyframe.

Scorer PASS là điều kiện cần. Agent còn xem contact sheet toàn bộ overlay, crop nghi ngờ và boundary `start-1 / start / end / end+1` cho cả 5 video.

## Invariant tổng quát đã bổ sung

Production (`master_phase1_extractor.py`):

1. Dense detector geometry không được relocate sang ink region rời nhau.
2. Caption ngắn không được hút one-sided/two-sided food texture balloon.
3. Với broad X balloon, detector giữ X authority; ink refinement giữ Y authority để không cắt outline/descender.
4. Same-text track gần như cùng lifespan dùng nested narrower geometry; track rộng chỉ đóng góp timing.
5. Hardsub purge chạy hai pha; sparse balloon bị reject không còn purge caption thật kế bên.
6. Raw pre-merge detector coverage là final X authority. Final box `≥1.8×` median per-frame detector union sẽ thu X về repeated detector core, giữ nguyên ink-refined Y.
7. Position lock + OCR ổn định không chứng minh text là editor overlay. Non-hardsub micro đứng một mình phải có editor-layout anchor/peer độc lập; nếu không drop bằng `isolated_micro_source_text` và giữ audit.

Scorer (`score_phase1_pass.py`):

1. Bắt buộc quality report, coverage, confirmed all và uncertain zero.
2. FAIL khi có dense uncovered hardsub span từ 3 frame.
3. FAIL khi final hardsub `≥1.8×` dense detector union core.
4. Adjacent thin shadow có thể được active final hardsub giải thích.
5. Raw hit khớp strong rejected gate (`local_text_reject`, `low_ink`, `not_overlay_geometry`, `scene_text`, `scene_ui_cluster`) chỉ được coi là detector shadow khi có confirmed final hardsub active cùng Y band. Không có active final track thì vẫn FAIL.
6. FAIL nếu final timeline còn candidate vi phạm invariant isolated-micro provenance.
7. FAIL nếu local OCR đọc được ít nhất hai CJK với confidence `>=0.90` nhưng local semantic gate vẫn reject; đây là recall-review evidence, không được biến mất sau một scorer PASS.

## Provenance correction sau phản hồi operator

Hai ảnh operator đưa chỉ là ví dụ, nên audit không dừng ở đúng các box đó. V54 bị hạ từ 5/5 xuống 3/5 khi scorer mới tìm thấy source/scene candidates trong hai video. V55 rerun:

- `7472735913513078057`: 37 → 34 track; ba drop `isolated_micro_source_text` (một chữ in trên thiết bị và hai scene highlight/texture).
- `7503536530008722698`: 71 → 70 track; printed stove instruction của v54 không còn trong SSOT.
- Cả 238 retained tracks của mixed Random-5 đã được xem bằng full-frame provenance contact sheets ở `apps/api/tmp_phase1_provenance_audit_v55/`; subtitle, ingredient/recipe label và nutrition endcard đều còn.

Giới hạn cần nói đúng: từ một video raster đã flatten, source-print đứng yên và editor-overlay đứng yên có thể giống hệt nhau về quan sát. Muốn bảo đảm provenance 100% cần clean pre-edit source/layer metadata, hoặc fail-closed review cho candidate mơ hồ; không được dùng screen lock làm bằng chứng duy nhất.

## Recall correction v58 sau bốn ảnh operator

V55 vẫn bỏ hai editor labels dù raw DBNet và local OCR đều nhìn thấy:

- `150g里脊肉`: OCR confidence `0.996`;
- `250g虾仁`: OCR confidence `0.992`.

Gate cũ chỉ nhận ASCII unit nếu `g/ml` nằm cuối chuỗi. V58 nhận measurement token ở giữa amount và CJK name, hợp nhất các OCR variants `250g仁 / 230g仁 / 250g虾仁` thành một lifespan nhưng không gộp ingredient name khác. Box `三个鸡蛋` lấy supported 10th-percentile left evidence + bounded pad (`x0≈504.3`), và bottom shadow 2-hit bị dense hardsub host loại.

Sequential-frame audit xác nhận:

- spinach `125–189`;
- eggs `138–189`;
- pork `139–189`;
- shrimp `153–189`;
- cabbage `168–189`.

Artifact: `tmp_phase1_random5_final_v58/7503536530008722698/qa/frame_recall_sequential/ingredient_boundaries_contact.jpg`. OpenCV random seek trả frame `N-1` trên MP4 này, nên không dùng random seek để phán exact boundary.

## Hai lỗi mới tìm được trong vòng cuối

### 1. Synthetic wide box sau merge/split

Video `7472735913513078057`, track `196–219`:

```text
prior  [438, 1001, 1414, 1051]
result [812.85, 1001, 1113.15, 1051]
```

Track-local hit median bị nhiễu bởi nhiều fragment cùng frame. Chốt cuối chuyển sang raw coverage độc lập trước merge. Visual xác nhận box mới đủ toàn bộ `食用油一勺`, không dư nền; boundary `195 OUT / 196 IN / 219 IN / 220 OUT`.

### 2. Coverage shadow không phải missing caption

Video `7503536530008722698`:

- `882–885`: food blob rất cao, audit `not_overlay_geometry`;
- `1201–1205`, `1213–1216`: phản sáng đáy chảo, local OCR rỗng, audit `local_text_reject`.

Frame gốc cho thấy không có caption thứ hai; caption thật `sub_22`/`sub_28` vẫn được final timeline cover đúng. Scorer chỉ miễn các shadow này theo strong-gate + active-caption invariant ở trên.

## Kiểm thử cuối

```text
test_master_phase1_extractor.py: 79 PASS
test_phase1_text_gates.py: 38 PASS
test_phase1_score.py: 8 PASS
test_phase1_pass_contract.py: 44 PASS
python -m unittest discover -s tests -p "test_phase1_*.py": 98 PASS
```

## Artifact review

Mỗi thư mục video chứa:

- `master_timeline.json`;
- `text_frame_coverage.json`;
- `qa/quality_report.json`, `qa/before_after.json`;
- `qa/overlays/`, `qa/boundaries/`, `qa/boundary_crops/`;
- contact sheets được tạo trong `qa/contact_sheet_overlays.jpg` và `qa/contact_sheet_boundaries.jpg` cho các lượt audit cuối.

## Closing regression — v58 operator PASS

Fresh STEP=1 reruns after final temporal reconciliation:

| Video | Tracks | Hardsub | Confirmed / uncertain | Temporal reconciliation | Scorer |
|---|---:|---:|---:|---|---|
| `7472735913513078057` | 34 | 15 | 34 / 0 | no change | PASS |
| `7604099786644380635` | 35 | 16 | 35 / 0 | no change | PASS |
| `7543241784286465306` | 50 | 20 | 50 / 0 | no change | PASS |
| `7503536530008722698` | 71 | 27 | 71 / 0 | extend 2 fade frames | PASS |
| `7632302211641623154` | 49 | 20 | 49 / 0 | no change | PASS |

Output roots:

```text
apps/api/tmp_phase1_random5_final_reconcile_v58/            # 747, 760, 750, 763
apps/api/tmp_phase1_random5_final_reconcile_v58_edge_fix/   # 754
```

Additional holdout `7450099336215579915`: 694 frames, 36 tracks, 36/0 confirmed/uncertain, scorer PASS. The new audit trims `sub_02` from `0–11` to `0–2` and extends the hardsub fade tail from frame `230` through `233`; frame `234` is out at the scene cut.

Regression evidence:

```text
test_master_phase1_extractor.py: 84 PASS
python -m unittest discover -s tests -p "test_phase1_*.py": 98 PASS
test_phase1_text_gates.py: 38 PASS
test_phase1_score.py: 8 PASS
test_phase1_pass_contract.py: 44 PASS
test_master_phase1_phase2_ocr.py: 14 PASS
test_ocr_translate_gate.py: 7 PASS
test_analyze_ocr_ske_bridge.py: 2 PASS
test_run_phase2_only.py: 2 PASS
```

The Phase 2 artifact bridge smoke uses `python -m scripts.run_phase2_only --mock <copy-of-phase1-output>`. This flag directly selects mock OCR and prevents an external OCR call. The smoke is a contract test only; mock text is intentionally rejected by the translate content gate.

This is **operator PASS**. Phase 1 is frozen at v58/STEP=1; Phase 2 must consume `master_timeline.json` without changing geometry or timing.

## Việc còn lại

Không còn gate đóng Phase 1. Công việc tiếp theo thuộc Phase 2 OCR. Chỉ mở lại Phase 1 khi có bằng chứng geometry/recall mới; không vá theo clip.
