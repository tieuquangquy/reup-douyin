# Localization Reup Pipeline — Product Design (Free Stack)

**Cập nhật lần cuối:** 2026-07-15  
**Trạng thái:** Quyết định sản phẩm đã khóa (thiết kế). Chưa bắt buộc triển khai code trong doc này.  
**Đọc kèm:** `docs/phase5-operator-pipeline.md`, `docs/audio-analysis-pipeline.md`, `docs/tts-pipeline.md`, `docs/download-pipeline.md`, `RULE.md`

| | |
|---|---|
| **Mục tiêu** | Reup số lượng lớn, chất lượng cao: hình + lời thoại + subtitle → video tiếng Việt sẵn đăng |
| **Ràng buộc** | Công cụ **miễn phí**, chất lượng cao nhất có thể trong nhóm free |
| **Chế độ** | Tự động A→Z **hoặc** bán tự động (checkpoint review) |
| **Đầu vào** | Video Douyin **no-logo**, **max height/quality** đã download (operator storage) |
| **Không làm (phase này)** | Lip-sync miệng, provider trả phí, SaaS multi-tenant, connector đăng live |

---

## 1. Tầm nhìn sản phẩm

Operator lấy video Douyin, hệ thống tạo bản Việt:

1. Giữ hình gốc (chỉ xử lý vùng chữ trên hình khi cần).
2. Thay lời thoại Trung bằng lời Việt sát nghĩa, khớp khung thời gian.
3. Che / xóa chữ Trung trên khung hình (và thumbnail), đè chữ Việt.
4. Render file cuối + đặt tên theo cấu trúc + lưu folder chuẩn.
5. Cho phép dừng ở vài điểm để chỉnh tay trước khi tốn GPU render.

Repo đã có khung job / transcript / TTS / render (placeholder providers). Doc này **khóa hướng sản phẩm + stack free** để các lần implement sau cùng một chuẩn.

---

## 2. Luồng chính (end-to-end)

```text
DOWNLOAD (no-logo, max quality)          ← đã có nền
        │
        ▼
┌───────────────────────────────┐
│ A. ANALYZE_AUDIO_GATE           │  VAD + tách audio + Demucs
│    → has_speech / skip_dubbing  │
└───────────────┬───────────────┘
                │
       có thoại │          không thoại
                ▼                ▼
┌──────────────────┐      giữ audio gốc
│ B. ASR (zh)        │      (hoặc chỉ background)
│  + segment timing  │              │
└────────┬─────────┘              │
         ▼                        │
┌──────────────────┐              │
│ C. DỊCH VI         │              │
│  Checkpoint #1     │              │
└────────┬─────────┘              │
         ▼                        │
┌──────────────────┐              │
│ D. TTS VI + mix    │              │
│  Checkpoint #2     │              │
└────────┬─────────┘              │
         └───────────┬────────────┘
                     ▼
┌──────────────────────────────────┐
│ E. ON-SCREEN TEXT + thumbnail      │
│    OCR → inpaint/blur → đè Việt    │
│    Checkpoint #3                   │
└────────────────┬─────────────────┘
                 ▼
┌──────────────────────────────────┐
│ F. RENDER FINAL + naming/folder    │
│    Checkpoint #4 → publish draft   │
└──────────────────────────────────┘
```

Video **không có thoại**: nhánh B–D (dubbing) **bỏ qua**; vẫn chạy E nếu có chữ trên hình, rồi F.

---

## 3. Quy tắc sản phẩm (đã chốt)

### 3.1 Audio — không đè voice lên track gốc nguyên khối

1. Tách **vocal** + **background** (Demucs).
2. Bỏ vocal Trung.
3. Mix **TTS Việt** + **background gốc**.
4. Chuẩn hóa âm lượng (EBU R128 / ffmpeg `loudnorm`) để đồng đều giữa các video.

### 3.2 Lệch độ dài Trung → Việt (khó nhất)

**Không** dịch cả bài rồi ép. Dùng **segment-level dubbing loop**:

1. ASR trả về từng câu + `start` / `end` → mỗi câu có ngân sách thời gian.
2. LLM dịch **từng segment** với ràng buộc độ dài (ước lượng ~4–5 âm tiết tiếng Việt / giây).
3. TTS segment → đo duration thật.
4. Lệch ≤ ~15%: co giãn `atempo` / rubberband trong khoảng **0.9–1.15**.
5. Lệch > ~15%: gọi lại LLM viết ngắn/dài hơn (1–2 vòng), rồi TTS lại.
6. Câu ngắn hơn slot: chấp nhận silence phần dư — không kéo dãn quá đà.

**Không làm** lip-sync khung miệng trong phase này.

### 3.3 Subtitle / chữ trên hình

| Loại | Cách xử lý |
|------|------------|
| **Hard subtitle** (phụ đề burn, vị trí ổn định) | Sample 2–5 fps (không OCR 30fps); gom sự kiện text + thời gian; xóa/inpaint vùng → đè Việt |
| **Chữ trong cảnh** (biển, áo, UI trong video) | Detect → đưa **review**; không auto che hết (dễ hỏng hình) |
| **Thumbnail** | OCR + inpaint ảnh tĩnh + đè Việt (cùng nội dung khi liên quan) |

Ưu tiên **inpaint** (VSR/STTN/LaMa) cho vùng hard-sub; **blur** là fallback nhanh.

### 3.3a DialogueBeat — authority thời gian cho thoại + dịch (mở đầu cho sub/OCR/TTS)

Mỗi **beat** = một nhịp thoại trên timeline video:

- `start_ms` / `end_ms` (neo khung hình sau này)
- `source_zh` do **máy chuẩn bị** (Demucs vocal → FunASR + đối chiếu caption Douyin)
- `translation_vi` sát nghĩa 1–1, **không thêm chữ**, cùng cửa sổ thời gian

**Machine-first (pilot — operator không cần biết tiếng Trung):**

1. **Phase A — ASR only:** `ANALYZE_AUDIO` (`skip_translation=true`) → Demucs vocal (khi có) → FunASR → **caption↔ASR consensus (ASR-first: caption chỉ gắn flag, không thay text thoại)** → auto-approve beats. FunASR unavailable/timeout/empty → `dialogue_phase=no_dialogue`, không cắt caption thành thoại.
2. **Operator QC bằng tiếng Việt:** Timeline + cột VI; chữ Trung chỉ đọc / tham chiếu. Flag `caption_asr_conflict` / `source_unverified` cảnh báo rủi ro.
3. **Phase B — Literal translate:** `BUILD_TRANSLATION_DRAFT` → `literal_safe` per beat, **không** chạy lại FunASR. Video không thoại: bỏ qua dubbing.

Bước phụ đề / OCR theo khung hình / TTS sau này chỉ **join theo beat + cửa sổ ms**, không tự cắt lại timeline.

### 3.4 Tự động vs bán tự động

| Checkpoint | Nội dung | Vì sao |
|------------|----------|--------|
| #1 Text | Máy chốt Source timed → dịch literal → sửa VI | Operator không QC Trung; timeline ổn định cho frame sync |
| #2 Audio | Nghe mix TTS + BGM | Phát hiện giọng lỗi / lệch slot xấu |
| #3 Visual | Xem vùng OCR/inpaint + overlay | Tránh che nhầm mặt / logo |
| #4 Final | So sánh nguồn vs render | Gate trước publish draft |

**Auto A→Z:** bỏ qua #1–#3 khi batch tin cậy; vẫn ghi log/warning để audit.  
**Bán tự động (mặc định pilot):** bắt buộc #1; #2–#3 bật khi operator chọn.

---

## 4. Stack miễn phí (đã khóa)

| Bước | Công cụ | Ghi chú |
|------|---------|---------|
| VAD | **Silero VAD** | Rẽ nhánh có/không thoại |
| Stem split | **Demucs `htdemucs_ft`** | Chuẩn ngành, open source |
| ASR zh | **FunASR Paraformer-zh** | Primary cho tiếng Trung |
| Align / word timing | **WhisperX** (khi cần timestamp mịn) | Bổ trợ FunASR |
| Dịch zh→vi | **Gemini API free tier** (chính) + **Qwen2.5 local (Ollama)** (fallback) | Prompt ràng buộc độ dài; không dùng Google Translate làm mặc định |
| TTS vi | **edge-tts** (`vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`) | Free; cùng neural Azure; operator chọn giọng |
| Fit thời lượng | ffmpeg `atempo` / **rubberband** | Clamp 0.9–1.15 |
| Denoise (tuỳ chọn) | **DeepFilterNet** | TTS thường đã sạch |
| OCR zh | **PaddleOCR (PP-OCRv4)** | Vùng + text |
| Xóa hard-sub video | **video-subtitle-remover (VSR)** | STTN / LAMA / ProPainter |
| Thumbnail inpaint | **LaMa** | Ảnh tĩnh |
| Mix / render | **ffmpeg** (+ NVENC nếu có) | `loudnorm` |

### 4.1 Abstraction trong repo

Giữ interface đã có trong `docs/audio-analysis-pipeline.md` / `docs/tts-pipeline.md`:

- `SourceSeparationProvider` → Demucs
- `SttProvider` → FunASR (+ WhisperX align khi cần)
- `TranslationProvider` → Gemini free / Qwen local
- `TtsProvider` → edge-tts (thay PlaceholderTone)

Local path / API key (nếu Gemini) chỉ qua env; không hardcode path máy operator.

### 4.2 Phần cứng khuyến nghị

- GPU NVIDIA ~**8GB+ VRAM** cho Demucs + FunASR + VSR ở chất lượng tốt.
- VRAM thấp hơn: vẫn chạy được với model nhỏ hơn / chậm hơn; không đổi contract pipeline.

---

## 5. Output & lưu trữ

- **Input đã chốt đường:** `LOCAL_STORAGE_ROOT` → `data/storage/workspace_*/dy/@handle__*/…__{height}p__nl.mp4`  
  (staging Playwright `.douyin_profiles/download_staging` **không** phải output cuối).
- **Final render:** cùng workspace, dưới prefix video + subdir `renders/` (asset type `FINAL_RENDER_VIDEO` / `RENDER_OUTPUT` — theo `path_strategy` hiện có).
- **Tên file final (đề xuất chuẩn, implement sau):**  
  `{date}__{aweme}__{caption_slug}__vi__{height}p__{voice_id}.mp4`  
  (không đụng layout download trừ khi có quyết định migrate riêng).
- Sidecar khuyến nghị: transcript JSON current, translation draft, TTS timing map, OCR/subtitle events, render manifest.

---

## 6. Hạng mục bổ sung (bắt buộc cho số lượng lớn)

| Hạng mục | Mục đích |
|----------|----------|
| Dedup / fingerprint trước xử lý nặng | Tránh tốn GPU video trùng |
| Resume từng job step | Fail giữa chừng không chạy lại từ đầu |
| Loudness chuẩn giữa các video | Trải nghiệm đồng đều |
| Dịch caption / description đăng bài | Không chỉ body video |
| Job visibility (`/ops/jobs` + Worklist) | Lỗi có mã + message hành động được |
| Ma trận trạng thái rõ | empty / queued / running / waiting_review / failed / ready_to_export |

---

## 7. Thứ tự triển khai khuyến nghị (sau khi doc này được follow)

Khớp Phase 5 Milestone B, **không** nhảy vào OCR trước khi audio gate ổn:

| Thứ tự | Việc | PASS ngắn |
|--------|------|-----------|
| **1** | Analyze gate: Silero VAD + extract + Demucs (hoặc stub Demucs có flag) | Mỗi video có `has_speech` / stems; nhánh skip dubbing đúng — **wired 2026-07-15:** `MARK_MEDIA_READY` → `ANALYZE_AUDIO`; VAD gate + Demucs/Silero providers (execution deferred → heuristic/fallback) |
| **2** | **DialogueBeat machine-first** + Checkpoint #1 | Demucs vocal + FunASR + caption consensus → auto-approve → **literal translate** → operator sửa VI — **wired 2026-07-15:** `skip_translation=True`; consensus flags; VI-first Transcript UI |
| **3** | edge-tts + fit loop + mix BGM + loudnorm + Checkpoint #2 | Nghe được track Việt khớp slot cơ bản |
| **4** | Hard-sub OCR events + blur clean + overlay (VI burn at render) + Checkpoint #3 | Chữ Trung hard-sub được che trên cleaned plate; xem `docs/ocr-hardsub-pipeline.md` |
| **5** | Render final + naming + Final review (Phase 5 C) | 1 video E2E auto hoặc bán tự động |

Nối dây tối thiểu trước providers nặng: `START_PROCESSING` / download xong → Confirm media → enqueue `ANALYZE_AUDIO` (xem `docs/phase5-operator-pipeline.md` **5.B.3**).

---

## 8. Non-goals

- Lip-sync / face reenactment.
- ElevenLabs / Azure Speech trả phí / Google Translate làm mặc định.
- Auto che mọi chữ trong cảnh (chỉ review).
- OCR mọi frame 30fps.
- Extension Phase 4 harden (paused trừ khi ingest gãy).
- Publish connector live trước khi 1 video E2E ổn.

---

## 9. Liên kết docs kỹ thuật sẵn có

| Doc | Vai trò |
|-----|---------|
| `docs/download-pipeline.md` | Đầu vào no-logo / quality |
| `docs/audio-analysis-pipeline.md` | Job `ANALYZE_AUDIO`, providers, versioning |
| `docs/tts-pipeline.md` | Job `SYNTHESIZE_TTS`, fit status (bổ sung stretch + rewrite trong implement sau) |
| `docs/phase5-operator-pipeline.md` | Wiring UI/API/worker pilot |

Khi implement lệch doc provider cũ (placeholder), cập nhật `audio-analysis-pipeline.md` / `tts-pipeline.md` cùng PR — nguồn sự thật job contract vẫn ở đó; **doc này** là nguồn sự thật **sản phẩm + stack free**.

---

## 10. Prompt phiên mới (implement)

```text
Đọc docs/localization-reup-pipeline-design.md + RULE.md.
Không làm OCR/render trước. Bắt đầu bước 1: ANALYZE_AUDIO gate
(Silero VAD + audio extract + Demucs/provider interface) trên video đã download.
Test-first theo .cursor/rules/test-before-code-change.mdc.
```
