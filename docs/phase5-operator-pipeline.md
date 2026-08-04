# Phase 5: Operator Pipeline Pilot

**Cập nhật lần cuối:** 2026-07-17

**Đọc file này + `RULE.md` khi bắt đầu Phase 5.** Extension Hybrid Collect (Phase 4) **tạm dừng** — đủ dùng cho ingest; chi tiết: `docs/handoff-hybrid-collect-phase4.md`.

**Thiết kế localization (free stack, sau download):** `docs/localization-reup-pipeline-design.md` — ASR/dịch/TTS/OCR/render; không thay scope Phase 5 wiring.

**Nav IA (2026-07-17):** Operator Studio = Collect → Review → Queue → Edit → Final → Publish (+ Setup). Capture Inbox trên **Operator** (không Ops). Ops Console = Monitor + AI settings + Extension Manager + Swagger. Authority: `apps/web/src/lib/navigationConfig.ts`.

| | |
|---|---|
| **Scope** | `apps/web`, `apps/api`, `apps/worker` — luồng operator sau extension |
| **Rule** | `RULE.md` + `.cursor/rules/diagnose-before-fix.mdc` |
| **Mục tiêu** | Nối các module đã có thành pipeline thật: Capture Inbox → Review → Production → Publish draft |
| **Không làm** | Extension 4.5/4.7–4.9, provider media thật, SaaS, connector mới |

---

## Bối cảnh

Phase 1 repo đã có gần đủ module (ingest, score, review, jobs, transcript, render, publish). Phase 5 **không xây lại từ đầu** — mà **xác nhận + nối dây** những gì còn thiếu giữa các màn hình.

```text
Extension (Phase 4 — PAUSED ✅)
    ↓
Capture Inbox          ← Milestone A
    ↓ Promote
Review Board
    ↓ (chưa nối tự động) ← Milestone B
Reup Queue → Download → Transcript → TTS → Render
    ↓
Final Review → Publish Draft   ← Milestone C
```

---

## Nền đã có (không làm lại)

| Khối | Trạng thái | Đường vào |
|------|------------|-----------|
| Capture Inbox | UI + API + promote + test | `/selection/capture-inbox` (**Operator** nav → Work; legacy `/ops/extensions/douyin/capture-inbox` redirects) |
| Review Board | Lọc, Reup Score, bulk approve/reject | `/selection/review-board` (**Operator** shell) |
| Reup Queue / Export / Handoff | State machine + UI | `/selection/reup-queue`, `/publishing/export-packages` (**Operator** shell) |
| Transcript editor | Save, merge, split, timing | `/production/transcript-editor/{sourceVideoId}` |
| Final review | Compare, approve, mark publish-ready | `/production/final-review/{sourceVideoId}` |
| Publish draft | Caption, schedule, risk | `/publishing/drafts` |
| Jobs + worker | Download, audio, TTS, render, publish | `/ops/jobs` (**Ops** monitor), `apps/worker` |
| Demo seed | Pipeline trên fixture | `scripts/dev-reseed.ps1`, `docs/demo-flow.md` |

### Khoảng trống chính (Phase 5 phải lấp)

| Gap | Bằng chứng |
|-----|------------|
| Review Board không enqueue Reup Queue | `ReviewBoardPage.tsx` — bulk actions không gọi `enqueueReupCandidates` |
| `START_PROCESSING` chỉ đổi status | `reup_queue_service.py` — không tạo `DOWNLOAD_VIDEO` job |
| Downloads UI chưa có | `apps/web/src/app/production/downloads/page.tsx` — placeholder |
| Web thiếu API client pipeline jobs | `api.ts` — không có `createDownloadJob` / `createAudioAnalysisJob` / `createTtsJob` |
| Job chain tự động chưa có | Worker chạy từng job; không auto-chain download → audio → TTS → render |
| Provider media placeholder | STT/TTS/translation dùng fallback — **chấp nhận** trong Phase 5 để validate luồng |

---

## Milestone A — Ingest → Review (tuần 1, ít hoặc không code)

**Mục tiêu:** Extension data đi được tới Review Board.

### Checklist

| ID | Công việc | Chi tiết | PASS |
|----|-----------|----------|------|
| 5.A.1 | Setup hàng ngày | `.\scripts\dev-doctor.ps1` → `dev-migrate` → `dev-start` | Web + API + **worker** chạy |
| 5.A.2 | Audit Capture Inbox | Mở session extension đã collect | Item có thumbnail, caption, `aweme_id`, metrics |
| 5.A.3 | Promote thử | Promote 10–20 item **ready** | `PROMOTED`, có `promoted_video_candidate_id` |
| 5.A.4 | Review Board | Keep 3–5, reject vài cái | Candidate hiện, score + metadata đúng |
| 5.A.5 | Pilot report | `.\scripts\new-pilot-report.ps1 -Name pilot-001` | Ghi skip reason, bottleneck |

### File debug khi promote fail

- `apps/api/src/services/capture_inbox_service.py` — gate promote (thumbnail, caption, status)
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`

### Rủi ro đã biết

Promote skip item thiếu thumbnail/caption. Sửa ở API/metadata normalization — **không** quay lại extension trừ khi collect thiếu field.

---

## Milestone B — Review → Production (tuần 2–3, wiring chính)

**Mục tiêu:** Operator không cần Swagger/API thủ công để chạy download → transcript → render.

### P0 — Bắt buộc

| ID | Công việc | File chính | PASS |
|----|-----------|------------|------|
| 5.B.1 | Review Board → Reup Queue | `ReviewBoardPage.tsx`, `apps/web/src/lib/api.ts` | Nút “Send to queue” sau approve; gọi `enqueueReupCandidates` |
| 5.B.2 | Start processing → download job | `reup_queue_service.py`, `download_service.py` | `START_PROCESSING` tạo job `DOWNLOAD_VIDEO`; queue → `WAITING_FOR_MEDIA` |
| 5.B.3 | Chain job tự động | `job_runner.py` hoặc orchestrator mới | Download xong → `ANALYZE_AUDIO` → `SYNTHESIZE_TTS` → `RENDER_FINAL` |
| 5.B.4 | Downloads page thật | `production/downloads/page.tsx` | List video + asset status; link transcript editor |
| 5.B.5 | Web API pipeline jobs | `api.ts` | `createDownloadJob`, `createAudioAnalysisJob`, `createTtsJob` |
| 5.B.6 | Job visibility | Transcript/Final review pages, `/ops/jobs` | Job queued/running/failed có mã lỗi |

### P1 — Pilot ổn hơn

| ID | Công việc | PASS |
|----|-----------|------|
| 5.B.7 | Transcript editor actions | Nút Generate TTS / Render (sau save) |
| 5.B.8 | Final review polling | Sau rerender, UI đợi `RenderOutput` mới |
| 5.B.9 | Pipeline dashboard | `/ops/pipeline` hiện backlog download/transcript/render |
| 5.B.10 | Douyin-aware download | URL từ extension; lỗi rõ khi CDN hết hạn |

---

## Milestone C — Final review → Publish draft (tuần 3–4)

| ID | Công việc | PASS |
|----|-----------|------|
| 5.C.1 | 1 video end-to-end | Promote → queue → download → transcript → render → final review |
| 5.C.2 | Publish draft | Mark publish-ready + tạo draft; risk scan trước mark-ready |
| 5.C.3 | Pre-beta suites | Suites 4–11 trong `docs/pre-beta-test-plan.md` |
| 5.C.4 | Go/no-go sơ bộ | `docs/go-no-go-criteria.md` — light pilot 1 session |

**Publish live (Facebook):** `docs/continuation-handoff.md` Step 23 — **sau** Milestone C ổn với 3–5 video.

---

## Thứ tự làm khuyến nghị

```text
Tuần 1 — validation (ít code)
  5.A.1 → 5.A.5
  Nếu promote fail nhiều → sửa metadata gate API

Tuần 2 — nối dây (ROI cao)
  5.B.1 Review → Queue
  5.B.2 Start → Download job
  5.B.4 Downloads page
  5.B.6 Job visibility

Tuần 3 — chain + 1 video E2E
  5.B.3 Job chain
  5.B.5 Web API jobs
  5.C.1 Một video hoàn chỉnh

Tuần 4 — pilot + polish
  5.C.2 → 5.C.4
  5.B.7–5.B.10 tùy pain operator
```

---

## Tiêu chí “Phase 5 xong”

| Mức | Định nghĩa |
|-----|------------|
| **Tối thiểu** | 10 promote → 3 keep → **1 video** qua transcript → render → final review → publish draft (placeholder media OK) |
| **Pilot** | Light load 10–20 video/ngày; operator không cần dev; lỗi thấy trong `/ops/jobs` |
| **Pre-beta** | Không ambiguous render state; không silent job fail — `docs/pre-beta-test-plan.md` blockers |

---

## Non-goals (Phase 5)

- Extension Phase 4.5, 4.7–4.9 (deferred)
- Provider thật (Whisper, TTS thật, dịch thật)
- Redis queue / multi-tenant SaaS
- Connector TikTok / YouTube
- Refactor worker handlers (trừ khi job không chạy)

---

## Load levels (pilot)

Theo `docs/operator-pilot-workflow.md`:

| Level | Volume | Kỳ vọng |
|-------|--------|---------|
| Light | 10–20 video/ngày | 3–5 keep; 1–3 tới final review |
| Medium | 30–50 video/ngày | 8–15 keep; 3–8 process sâu |
| Heavy | 80–100+ | Stress signal; không phải promise Phase 1 |

---

## Bước đầu tiên (hôm nay)

1. `.\scripts\dev-doctor.ps1` → `.\scripts\dev-start.ps1`
2. Mở `/selection/capture-inbox` — batch đã collect
3. Promote 5 video → `/selection/review-board`
4. Ghi: promote OK / skip count / lý do skip

Nếu PASS → Milestone A tuần 1 xong; bắt đầu **5.B.1**.

---

## Tài liệu liên quan

| Doc | Dùng khi |
|-----|----------|
| `docs/handoff-hybrid-collect-phase4.md` | Extension ingest (paused) |
| `docs/operator-pilot-workflow.md` | Quy trình hàng ngày, metrics |
| `docs/local-operator-guide.md` | Setup ngắn |
| `docs/demo-flow.md` | Demo seed không cần Douyin live |
| `docs/pre-beta-test-plan.md` | Suite validation |
| `docs/go-no-go-criteria.md` | Trước publish connector thật |
| `docs/continuation-handoff.md` | Step 23+ publish pilot |
| `docs/templates/daily-operator-log-template.md` | Log pilot |

---

## Prompt phiên mới (Phase 5)

```
Đọc docs/phase5-operator-pipeline.md và RULE.md.
Tiếp tục: [ID công việc, ví dụ 5.B.1].
Bằng chứng: [screenshot / API response / job id / error code].
```
