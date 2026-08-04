# Phase 4 adaptive render và output QA

Phase 4 biến contract OCR/bản dịch đã duyệt thành video tiếng Việt. Luồng này local-first, giữ ranh giới rõ giữa authority đầu vào, render, QA sau encode và operator review. Không có rule nào được phép gắn với video ID, `text_id`, frame hoặc tọa độ của một fixture cụ thể.

## Authority đầu vào

Preflight kiểm tra chuỗi SHA-256 trên đĩa trước khi tạo render input:

1. `master_timeline.json` được Phase 2 tham chiếu.
2. `phase2_ocr_timeline.json` và `phase2_handoff.json`.
3. `phase3_translation_timeline.json` đã được duyệt.
4. `phase3_render_handoff.json` có trạng thái `READY_FOR_RENDER`.
5. Source video được Phase 1 tham chiếu.
6. PTS map cho video VFR.
7. `phase4_visual_approval.json` cho final render.
8. `RENDER_PREP_MANIFEST_V2` và joined Vietnamese TTS đã `AUDIO_APPROVED`.

Mọi render track join bằng exact `text_id`. Không dùng nearest-neighbor, fuzzy text lookup hay `[VI mock]`. Visual preview được phép giữ source audio; final render bắt buộc dùng audio authority TTS đã duyệt và hash phải khớp file thực tế.

## Luồng operator

Chạy từ `apps/api`:

```powershell
python -m scripts.run_phase4_preflight <phase3-output-directory>
python -m scripts.run_phase4_adaptive <phase3-output-directory>
python -m scripts.run_phase4_approval visual <phase3-output-directory> --operator <operator-id>

python -m scripts.run_phase4_approval stage-audio-from-db <phase3-output-directory> <source-video-uuid>
# Operator nghe phase4_joined_narration.wav.
python -m scripts.run_phase4_approval audio-from-db <phase3-output-directory> <source-video-uuid> --operator <operator-id>

python -m scripts.run_phase4_preflight <phase3-output-directory>
python -m scripts.run_phase4_adaptive <phase3-output-directory> --final
```

Không chạy lệnh `audio-from-db` trước khi operator nghe và chấp thuận audio.

## Render policy

- Tách `cover.roi` khỏi `layout.safe_area`; xóa chữ nguồn và đặt chữ Việt là hai authority khác nhau.
- Role-aware policy cho hardsub, title, UI label và dense endcard.
- Mask hardsub giãn theo chiều cao glyph để xóa cả outline/shadow.
- Mỗi track pre-seed mask từ start/middle/end để xử lý fade-in/fade-out và tránh cache mask thiếu.
- Title có thể dùng clean reference plate; background động dùng temporal flow và spatial fallback.
- Reference plate chỉ được seed khi vùng ngoài ROI ổn định và vùng chữ thay đổi rõ hơn nền. Candidate vẫn chứa overlay hoặc thuộc cảnh khác bị loại cứng; renderer fallback spatial thay vì chép chữ nguồn trở lại.
- Typography responsive, tối đa hai dòng cho hardsub/title, giữ nhóm số-unit và fail-closed khi chữ không còn đọc được.
- UI layout giữ tâm theo hàng nguồn; role `ui_chip` được ưu tiên hơn nhãn hardsub nhiễu. Transition UI cùng vùng tối đa sáu frame được giao cho track đến sau, còn va chạm typography chỉ block khi phần giao chiếm ít nhất 8% nhãn nhỏ hơn.
- PTS được giữ qua PyAV; audio mux tường minh; metadata BT.709 được sao chép.
- Anti-transform tắt mặc định và không liên kết với chất lượng localization.

## Hardware encoder an toàn

Final render dùng `RENDER_VIDEO_ENCODER=auto` theo mặc định. Worker chạy một smoke encode thật thay vì chỉ tin danh sách `ffmpeg -encoders`:

- Windows: thử `h264_nvenc`, sau đó `h264_qsv`.
- macOS: thử `h264_videotoolbox`.
- Nếu hardware/driver không khả dụng: dùng `libx264`.

Khi hardware encoder được chọn, adaptive renderer ghi frame đã xử lý vào intermediate FFV1 lossless có PTS, rồi FFmpeg encode H.264 với `fps_mode=passthrough`. Cách này giữ authority VFR/PTS; không biến raw frame pipe thành CFR. Nếu final hardware encode lỗi sau khi probe đã PASS, renderer retry chính intermediate đó bằng `libx264`, không chạy lại OCR/inpaint và không thay đổi geometry đã duyệt.

Các biến cấu hình:

- `RENDER_VIDEO_ENCODER=auto|libx264|h264_nvenc|h264_qsv|h264_videotoolbox`
- `RENDER_HARDWARE_ENCODER_SMOKE_PROBE=true`
- `RENDER_HARDWARE_ENCODER_FALLBACK_ENABLED=true`

`phase4_render_recipe.json` ghi policy được yêu cầu và xác nhận `geometry_transform=none`, `color_transform=none`, `invisible_perturbation=false`. `phase4_adaptive_render_meta.json` và render QA ghi encoder thực tế, probe evidence, fallback, FFmpeg version, thời gian encode và SHA-256 output.

Concurrency hiện được chặn ở hai lớp: `RENDER_FINAL_MAX_CONCURRENT_RUNNING=1` theo job type và `GPU_MAX_CONCURRENT_RUNNING=1` dùng chung giữa OCR, TTS, preview và final render. Chỉ tăng các ngưỡng sau khi đo VRAM/encoder sessions trên máy đích.

## Audio final

Joined narration là WAV full-duration, mono PCM s16le 48 kHz. Nếu manifest có một stem Demucs `no_vocals.wav` đã hash-verify, renderer trộn stem đó ở gain cấu hình bởi `RENDER_BACKGROUND_MIX_GAIN` (mặc định `1.0`, giữ nguyên stem trước bước loudness normalization). Nếu không có stem, final dùng narration-only. Original Chinese vocal track không bao giờ được trộn lại.

Với analysis cũ chưa lưu background stem, có thể recovery mà không rerun Translation/TTS: chạy Demucs two-stem trên source, sau đó dùng `python -m scripts.run_phase4_approval attach-background <artifact-root> <no-vocals.wav> --operator <operator-id>`. Lệnh này giữ nguyên narration hash, bind SHA-256 của stem, ghi `phase4_background_attachment.json`, cập nhật manifest sang chiến lược mix và yêu cầu preflight lại trước final render. Không được dùng original audio thay cho `no_vocals.wav`.

Final encode áp dụng FFmpeg loudness normalization, mặc định mục tiêu `-14 LUFS` và true peak `-1.5 dBTP`. Cấu hình nằm ở `RENDER_LOUDNESS_NORMALIZATION_ENABLED`, `RENDER_LOUDNESS_TARGET_LUFS` và `RENDER_BACKGROUND_MIX_GAIN`. Output QA giữ tham chiếu `-14 LUFS` cho narration/TTS; riêng authority `preserve_verified_no_dialogue_source_audio` dùng tham chiếu music-safe `-16 LUFS` để giữ headroom và dynamic range của nhạc/hiệu ứng gốc, trong khi duration, true peak và measurement-complete vẫn fail-closed như bình thường.

## Output QA sau encode

QA đọc lại source và MP4 đã encode, không tin riêng diagnostics trong RAM. Nó chọn tối đa 20 frame theo global/track start-middle-end và motion peak, rồi kiểm tra:

- duration và frame count;
- color range, color space, transfer và primaries;
- thay đổi ngoài union của cover ROI và text safe area;
- temporal flicker tăng thêm so với chuyển động source;
- residual CJK bằng DBNet ONNX và local PP-OCR;
- audio stream tồn tại trong final;
- audio duration khớp video;
- integrated loudness gần tham chiếu `-14 LUFS` cho narration/TTS hoặc `-16 LUFS` cho nguồn đã xác minh không có thoại;
- true peak/clipping và kết quả đo loudness FFmpeg đầy đủ;
- original/rendered samples và contact sheet cho operator.

Residual OCR vẫn fail-closed trong mọi ROI localization. Một ngoại lệ hẹp chỉ áp dụng cho chữ in vật lý vốn có trên source ở gutter mép khung: detection phải nhỏ, khớp source cùng frame về geometry và ký tự CJK, đồng thời không giao bất kỳ cover ROI đang active nào. Những detection này được ghi riêng vào `source_intrinsic_exclusions`, không bị xóa khỏi audit. Chữ ở trung tâm, chữ số-unit hoặc bất kỳ detection nào nằm trong authority localization vẫn là lỗi blocking.

Thiếu model OCR, OCR runtime lỗi hoặc bất kỳ final-audio check nào thất bại đều là `FAIL`. Visual preview vẫn được giữ để chẩn đoán với trạng thái `VISUAL_PREVIEW_QA_FAILED`; final có QA failure mang `FINAL_OUTPUT_QA_FAILED` và không được handoff.

Khi operator xác nhận một residual là OCR false positive, lệnh `approve-residual-false-positive` tạo `phase4_residual_cjk_false_positive_approval.json` và bind SHA-256 của source, Phase 3 handoff, detection, token và visual evidence bất biến. Approval chỉ loại observation chính xác hoặc peer có cùng text, geometry overlap/area similarity tối thiểu 80% trong cửa sổ 0,5 giây; detection khác vẫn block. Raw detection và mọi exclusion luôn được giữ riêng trong artifact QA để audit. Output QA sau encode bắt buộc lấy lại frame evidence đã duyệt và kiểm tra lại cùng approval authority.

Nhánh texture false-positive tự động chỉ áp dụng cho một glyph CJK rất nhỏ ngoài localization authority, source/render gần như không đổi và OCR confidence thấp. Nếu source OCR cũng nhận cùng glyph, cả hai box phải trùng geometry và đều dưới ngưỡng confidence. Glyph high-confidence, box lớn hoặc detection trong cover authority vẫn fail-closed.

Ngay sau encode, renderer ghi `VISUAL_PREVIEW_OUTPUT_QA_PENDING` hoặc `FINAL_OUTPUT_QA_PENDING` cùng hash video. Nếu local OCR QA bị ngắt, chạy `python -m scripts.rerun_phase4_output_qa <artifact-root>` để QA lại video đã hash-bind mà không render frame lần nữa.

### Remediation residual CJK

Nếu preflight bị `BLOCKED_VISUAL_RESIDUAL_CJK`, không nới mask mù và không sửa `master_timeline.json`. Tạo proposal Phase 2 bổ sung từ chính bằng chứng source/render:

```powershell
python -m scripts.build_phase2_residual_remediation_proposal <phase3-output-directory>
```

Builder gom detection trùng giữa các sample frame, bắt buộc OCR lại source bằng local DBNet + PP-OCR, yêu cầu cùng signature số/CJK và xác nhận temporal window trên source. Với video VFR, frame evidence được decode tuần tự theo index thay vì random-seek OpenCV để tránh lấy nhầm hình. Proposal v2 hỗ trợ hai hành động fail-closed: thêm occurrence Phase 2 thật sự bị thiếu, hoặc mở rộng geometry của occurrence hiện hữu khi OCR nguồn xác nhận toàn dòng đã được operator duyệt nhưng box Phase 1 bị cắt cụt. Geometry override chỉ tồn tại trong remediation authority, không sửa `master_timeline.json`. Artifact `phase2_residual_remediation_proposal.json` tự bind SHA-256 của toàn chuỗi Phase 1 → Phase 4 và source video; crop review nằm trong `qa/phase2_residual_remediation/`. Proposal chỉ là gợi ý: chưa tạo authority thay đổi, chưa ghi OCR approval và chưa tái sử dụng translation approval cũ. Operator phải duyệt proposal trước khi materialize remediation và chạy lại Phase 2 → Phase 4.

Khi Phase 2 OCR lại crop đã mở rộng, guard chỉ cho phép một biến thể deletion-only rất hẹp: thiếu tối đa đúng một glyph, candidate còn ít nhất bốn ký tự và toàn bộ candidate phải là subsequence của signature đã nằm trong proposal được operator duyệt. Ký tự mới, substitution, đảo thứ tự hoặc thiếu nhiều hơn một glyph đều bị coi là candidate drift và dừng luồng.

Nếu một retry Phase 2 trả OCR rỗng cho track không nằm trong remediation, approval cũ chỉ được carry-forward khi file approval vẫn bind đúng Phase 1 hash, toàn bộ geometry ref đều có `ocr_source=failed`, candidate hiện tại rỗng và OCR text cũ không rỗng. Contract ghi `phase2_transient_ocr_failure_carry_v1` cùng review hash cũ/mới để audit. Track đang được remediated hoặc candidate khác rỗng không bao giờ đi qua nhánh này.

Sau khi operator duyệt đúng proposal hash:

```powershell
python -m scripts.materialize_phase2_residual_remediation <artifact-root> <proposal-json> --approve-proposal-sha <sha256> --operator <operator-id>
python -m scripts.run_phase2_only <artifact-root>
python -m scripts.rebind_phase3_approvals_after_residual_remediation <artifact-root> --stage
python -m scripts.run_phase3_only <artifact-root>
python -m scripts.rebind_phase3_approvals_after_residual_remediation <artifact-root>
python -m scripts.run_phase3_only <artifact-root>
python -m scripts.run_phase4_preflight <artifact-root>
```

Materialization tạo `phase2_residual_remediation.json`, không sửa master. Phase 3 carry-forward chỉ rebind quyết định cũ khi `content_id`, Chinese đã duyệt và candidate tiếng Việt đều khớp tuyệt đối; drift ở bất kỳ trường nào đều dừng. Mỗi lần Phase 4 preflight chạy lại, toàn bộ sample set cũ được chuyển vào `qa/stale/phase4_preflight_samples/` để manifest hiện hành không lẫn bằng chứng của lần chạy trước.

### Visual triage khi proposal tự động chưa đủ bằng chứng

Khi batch index trả `OPERATOR_TRIAGE_REQUIRED`, tạo pack đối chiếu mà không thay đổi authority:

```powershell
python -m scripts.build_phase4_residual_visual_triage <batch-run-root>
```

Builder kiểm tra lại hash của batch state, Phase 3 handoff, Phase 4 meta/report, proposal attempt và source video. Mỗi residual cluster có source/render ở frame chính cùng frame trước/sau, crop chặt, contact sheet và các geometry Phase 1 giao nhau (phân biệt giao cắt đang active với geometry chỉ trùng vị trí ở thời điểm khác). Frame nguồn luôn được decode tuần tự để an toàn với video VFR.

Các nhãn `REMEDIATE`, `FALSE_POSITIVE` và `NEEDS_OPERATOR_INPUT` chỉ là đề xuất fail-closed. Pack luôn ghi `operator_approval_written=false` và không tạo remediation, visual approval, TTS, render, export hay publish state. Operator phải quyết định dựa trên contact sheet trước khi quay lại luồng materialize remediation hoặc false-positive approval hiện có.

Sau khi đã đọc contact sheet, các sửa OCR/translation/geometry được ghi vào một curated input riêng của batch rồi validate bằng:

```powershell
python -m scripts.build_phase4_residual_triage_decision_proposal <batch-run-root> <curated-decisions.json> --output-stem <versioned-proposal-stem>
```

Decision builder bắt buộc có đúng một quyết định cho mọi cluster, kiểm tra lại hash của visual triage và toàn bộ frame/crop evidence. Dùng `--output-stem` versioned cho follow-up để không overwrite proposal đã materialize; materializer giữ nguyên path/hash của đúng file versioned được duyệt. `EXPAND_EXISTING_PHASE2_GEOMETRY` chỉ hợp lệ khi OCR Phase 2 và bản dịch Phase 3 đã duyệt vẫn khớp target. `MANUAL_TIGHT_GEOMETRY` phải nhỏ hơn box detector để tách glyph bị gộp. `MANUAL_EVIDENCE_GEOMETRY` được phép mở rộng box OCR partial theo contact sheet nhưng phải chứa ít nhất 80% residual, không quá 12 lần diện tích detector, không quá 2% frame và không vượt sáu lần mỗi chiều. Nhánh `SOURCE_INTRINSIC_PHYSICAL_TEXT` còn yêu cầu crop source/render gần như không đổi. Output proposal vẫn chỉ là đề xuất; token trong file phải được operator duyệt rõ ràng trước khi materialize bất kỳ thay đổi nào.

Artifact mới:

- `phase4_residual_visual_triage.json` và `PHASE4_RESIDUAL_VISUAL_TRIAGE.md` trong từng case;
- `qa/phase4_residual_visual_triage/<cluster-id>/` chứa source frame, crop và contact sheet hash-bound;
- `phase4_residual_visual_triage_index.json` và `PHASE4_RESIDUAL_VISUAL_TRIAGE_INDEX.md` ở batch root.

## Artifact

- `phase4_render_input_preview.json`: contract sau validation.
- `phase4_render_input.json`: chỉ có khi typography preflight đạt.
- `phase4_render_recipe.json`: recipe hash tái lập được.
- `phase4_pts_map.json`: PTS authority cho VFR.
- `phase4_visual_approval.json`: operator approval cho preview đã PASS QA.
- `phase4_residual_cjk_false_positive_approval.json`: approval OCR false-positive hash-bound; không phải rule bỏ qua toàn cục.
- `phase4_joined_narration.wav`: narration đã stage và hash-verify.
- `phase4_audio_staging.json`: trạng thái `PENDING_AUDIO_REVIEW`.
- `render_prep_manifest.json`: manifest staged hoặc approved.
- `phase4_audio_approval.json`: chỉ xuất hiện sau operator approval.
- `phase4_adaptive_visual_preview.mp4` hoặc `phase4_adaptive_final.mp4`.
- `qa/phase4_adaptive_*_output_qa.json`: verdict visual và audio sau encode.
- `phase4_adaptive_render_meta.json`: trạng thái handoff, checkpoint Output QA và refs artifact.

## Mức hoàn thành

`READY_FOR_PHASE4` chỉ xác nhận contract/preflight. `VISUAL_PREVIEW_RENDERED` xác nhận preview đã PASS output QA. `FINAL_RENDERED` chỉ xuất hiện khi cả `VISUAL_APPROVED`, `AUDIO_APPROVED`, hash authority và output QA đều PASS.

Một video PASS chỉ xác minh một fixture. Mức tin cậy “dùng cho mọi video” phải dựa trên corpus ở `docs/phase4-regression-corpus.json`, bao phủ nhiều bố cục, chuyển cảnh, duration, VFR/CFR, giọng TTS và điều kiện background khác nhau.
