# PROJECT CONTEXT HANDOFF

## 1. Project Overview

`reup-douyin` là một monorepo local-first dành cho một operator Windows trong Phase 1. Mục tiêu sản phẩm là hỗ trợ operator nhập/link hoặc capture nội dung từ Douyin, thu thập video ứng viên, lọc và chấm điểm tiềm năng reup, review trong UI, chuẩn bị/localize nội dung tiếng Việt, render/export, rồi hỗ trợ publish lên các nền tảng.

Người dùng chính hiện tại là operator nội bộ, không phải end-user public. Project được scaffold theo hướng SaaS-ready: dù Phase 1 chạy local, boundary đã tách frontend, API, worker, shared contract, storage abstraction, job orchestration để sau này có thể thêm multi-user auth, Redis queue, object storage, cloud deployment và connector publish khác.

Trạng thái tổng quát hiện tại:

- Web app Next.js đã có nhiều màn hình operator/ops ở mức alpha/pre-beta foundation.
- FastAPI backend đã có nhiều route/service/model/migration cho ingest, review, media, transcript, render, publish, risk, ops metrics, capture inbox và Douyin extension.
- Worker Python mới là local polling skeleton, chưa phải pipeline media/crawl thật.
- Chrome extension `extension-douyin-capture` đang được phát triển mạnh để capture/scan Douyin profile và đẩy metadata về backend. Gần nhất đã hoàn thành Phase `22C-9Z-3` để sửa stale watchdog của Scan Profile và ép legacy scanner chạy sau DOM Probe.

## 2. Current Architecture

### Frontend

Frontend nằm tại `apps/web`, dùng Next.js 15 + React 19 + TypeScript. Frontend chỉ sở hữu UI/operator interaction, gọi API qua `apps/web/src/lib/api.ts`, không crawl Douyin, không xử lý video nặng, không ghi DB trực tiếp.

Các nhóm UI chính:

- Operator home: `apps/web/src/components/operator-home` và `apps/web/src/app/page.tsx`.
- Intake/profiles/crawl sessions: `apps/web/src/app/intake/*`, `apps/web/src/components/intake`, `apps/web/src/lib/intakeState.ts`.
- Selection/review board/reup queue: `apps/web/src/app/selection/*`, `apps/web/src/components/review-board`, `apps/web/src/components/reup-queue`.
- Production checkpoints: transcript editor, final review, publish draft.
- Ops console: jobs, health, pipeline, accounts, assets, risk, publish control, optimization, Douyin extension manager/capture inbox.
- i18n: `apps/web/src/lib/i18n`, `apps/web/src/lib/i18n/en.json`, `apps/web/src/lib/i18n/vi.json`.

Navigation config nằm ở `apps/web/src/lib/navigationConfig.ts`, chia `operatorNavSections` và `opsNavSections`.

**IA (Phase 5 journey):** Operator = Capture Inbox → Review Board → Reup Queue → Transcript/Final (context) → Drafts/Export/Handoffs → Setup (accounts/extension). Ops = Monitor (home/pipeline/health/jobs) + AI settings (translation/caption/TTS) + Extension Manager + Swagger. Routes như Intake/Optimization/Publish Ops vẫn tồn tại qua URL nhưng không còn trên sidebar.

### Backend

Backend nằm tại `apps/api`, dùng FastAPI + SQLAlchemy + Alembic. Entry point là `apps/api/src/main.py`, include nhiều router:

- `jobs`, `source_ingest`, `candidates`, `downloads`, `audio_analysis`, `tts`, `renders`.
- `publish`, `publish_control`, `analytics`, `operations`, `optimization`, `pipeline_dashboard`, `risk`.
- `douyin_accounts`, `douyin_extension`, `capture_inbox`, `reup_queue`, `export_handoff`, `intake`.

Backend chịu trách nhiệm HTTP contract, validation, persistence coordination, job submission/state. Không nên chạy long-running processing inline trong route handler.

### Extension

Chrome extension nằm tại `apps/extension-douyin-capture`. Đây là surface quan trọng cho Douyin capture local:

- `src/background.ts`: background service worker, backend post, CDP/debugger capture, background-owned Scan Profile route, watchdog/finalization diagnostics.
- `src/contentScript.ts`: code chạy trong trang Douyin, detect page context, DOM probe, legacy profile scanner message handler, harvest runtime V2, calibration.
- `src/popup.ts`: popup UI/controller lớn cho capture, Scan Profile, Start Collecting, reset, calibration, debug diagnostics.
- `src/wholeProfileHarvest/*`: state machine và workflow chính cho whole-profile scan/collect/flush.
- `src/modalWholeProfileTest.ts`: chứa legacy scanner tốt đã được reuse: `collectProfileCardsUntilStable(...)`.

Extension build bằng TypeScript + esbuild, output vào `apps/extension-douyin-capture/dist`.

### Database/storage

Backend target là PostgreSQL. Alembic migrations nằm trong `apps/api/alembic/versions`. Models nằm trong `apps/api/src/models`. Storage Phase 1 là local disk qua abstraction; không nên hardcode path trong service workflow.

Các nhóm model chính gồm foundation/workspace, ingestion/source account, jobs, media, review/candidate, artifacts/transcript, publish, analytics, capture inbox, reup queue, export handoff.

### API/internal service

API service layer nằm trong `apps/api/src/services`, `audio_pipeline/services`, `render_pipeline/services`, `publish/services`, `publish_routing/services`, `risk/services`, `optimization/services`, `analytics/services`.

Adapters/provider abstraction:

- Douyin adapters: `apps/api/src/adapters/*`.
- Downloaders: `apps/api/src/downloaders/*`.
- Audio/TTS/render providers/runners are partly placeholder/mock-capable.

### Job/queue/state machine

Backend has job orchestration APIs and service state transitions. Worker currently has local polling runtime in `apps/worker/src/runtime.py` and mock handlers in `apps/worker/src/handlers/mock_handlers.py`. Redis-backed distributed queue remains future work.

Extension has a separate local state machine for whole-profile harvesting in `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts` and controller workflows in `controller.ts`. This state is persisted in Chrome storage under keys from `storageKeys.ts` / `wholeProfileHarvest/state.ts`.

### Main data flows

1. Web operator flow: browser UI -> `apps/web/src/lib/api.ts` -> FastAPI route -> service -> DB/storage -> response -> UI state/component.
2. Backend job flow: API route creates/updates job -> DB job rows/steps -> worker polling skeleton claims job -> placeholder handler updates state.
3. Extension capture flow: popup/background/contentScript on Douyin page -> extract DOM/CDP metadata -> POST to backend Douyin extension/capture inbox route -> backend stores capture session/items -> web capture inbox/review surfaces display data.
4. Whole Profile extension flow: popup action -> background-owned Scan Profile -> content script ping -> DOM Probe -> legacy scanner in content script -> queue adapter in controller -> local harvest queue -> Start Collecting/flush later.

## 3. Main User Flows

### Flow A: Review candidate trong web

1. Operator mở `/selection/review-board` hoặc `/review-board`.
2. UI gọi API qua `fetchCandidates(...)`, `fetchFilterPresets(...)` trong `apps/web/src/lib/api.ts`.
3. Backend route candidates đọc/filter candidate records, trả score breakdown và metadata.
4. Operator keep/reject/mark-next-step hoặc delete candidate.
5. Service cập nhật DB; UI refresh state.

### Flow B: Intake nguồn Douyin/profile

1. Operator vào `/intake`, `/intake/profiles`, hoặc `/intake/crawl-sessions`.
2. UI dùng `intakeState.ts` và API functions trong `api.ts` để discover/ready-check/preset.
3. Backend route `intake`/`source_ingest` dùng adapter Douyin để validate/normalize URL và map payload thành source profile/video/metrics.
4. Với connected Douyin account, docs/code hiện có hướng `browser-profile-backed fetch` là execution path chính khi `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true`; HTTP fetch chỉ là fallback khi browser profile/context không dùng được.
5. Cần kiểm tra thêm bằng browser profile thật: browser fetch vẫn có thể gặp challenge/login-required/parse-zero và không nên coi là crawler production-ready tự động.

### Flow C: Transcript editor -> final review -> publish draft

1. Operator chọn source video đã có media/transcript.
2. `/source-videos/[id]/transcript-editor` hoặc `/production/transcript-editor/[sourceVideoId]` tải transcript/translation draft.
3. Operator sửa segment/timing, merge/split, save/discard/rerun.
4. Render/prep/final review flow dùng render assets và metadata.
5. Publish draft screen tạo/chỉnh caption/CTA/hashtags/account/schedule ở mức operator-assist.

### Flow D: Douyin extension setup/capture inbox

1. Operator vào web `/setup/douyin-extension` hoặc `/ops/extensions/douyin` để xem hướng dẫn/trạng thái extension.
2. Operator reload unpacked extension từ `apps/extension-douyin-capture/dist`.
3. Trên Douyin, popup extension capture current page/profile hoặc whole profile harvest.
4. Backend Douyin extension routes nhận capture payload/session/items.
5. Web capture inbox ở `/selection/capture-inbox` review và chuyển item về review/reup queue.

### Flow E: Extension Scan Profile hiện tại

1. Operator mở Douyin profile có grid video và bấm Scan Profile trong popup.
2. Popup dispatch background route `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9I`.
3. `background.ts` tạo run id dạng `scan_profile_22C9Z3_*`, watchdog stage `resolving_tab`, và runtime diagnostics `22C-9Z-3`.
4. Controller `runScanProfileWorkflow(...)` resolve tab, ensure content script, ping ok.
5. Post-ping DOM Probe chạy bằng message `DOUYIN_PROFILE_DOM_PROBE_22C9I`, ghi `profile_dom_probe_status`, `profile_grid_ready`, `aweme_id_count`.
6. Nếu DOM Probe productive, background runtime gửi `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3` đến content script.
7. Content script gọi legacy scanner `collectProfileCardsUntilStable(...)` qua `runModalTestProfileScan(...)`.
8. Controller dùng adapter `legacy_verified_target_queue_adapter_22C9Z3` để build queue pending.
9. Diagnostics phải không còn `scan_profile_stage_timeout:resolving_tab` nếu stage đã tiến xa hơn.

## 4. Completed Work

### Monorepo foundation

- Mục tiêu: tách frontend/API/worker/shared/config/docs.
- File chính: `README.md`, `docs/architecture-overview.md`, root `package.json`.
- Trạng thái: hoàn thành scaffold local-first/SaaS-ready.
- Ghi chú: root scripts dùng PowerShell cho Windows local operator.

### Backend database/API foundation

- Mục tiêu: FastAPI HTTP boundary, SQLAlchemy models, Alembic migrations, service layers.
- File chính: `apps/api/src/main.py`, `apps/api/src/api/routes/*`, `apps/api/src/models/*`, `apps/api/alembic/versions/*`.
- Trạng thái: nhiều domain đã có route/service/test.
- Ghi chú: không đọc/ghi secret từ `.env`; dùng `.env.example` làm template.

### Candidate/review/reup queue foundation

- Mục tiêu: lọc/chấm điểm/review candidate và đưa vào queue.
- File chính: backend `candidates.py`, `reup_queue.py`, services candidate/reup queue; frontend `reviewBoardState.ts`, `captureInboxReupScore.ts`, components review/reup queue.
- Trạng thái: có UI, API, tests.
- Ghi chú: cần kiểm tra thêm flow dữ liệu production thực tế từ Douyin capture sang review board.

### Media/audio/TTS/render/publish foundation

- Mục tiêu: tạo pipeline local-first từ downloaded media đến transcript, TTS/subtitle, render, final review, publish draft.
- File chính: `audio_pipeline`, `tts_pipeline`, `render_pipeline`, `publish`, web transcript/final-review/publish-draft components.
- Trạng thái: foundation có tests; một số provider là placeholder/mock.
- Ghi chú: real STT/TTS/render/publish connector cần kiểm tra theo môi trường local.

### Operations/analytics/risk/optimization

- Mục tiêu: operator observability, publish health, risk policy, optimization hints.
- File chính: `apps/api/src/api/routes/operations.py`, `analytics.py`, `risk.py`, `optimization.py`, services tương ứng; web ops pages.
- Trạng thái: có API/UI/test foundation.
- Ghi chú: đây là analytics-lite/operator-assist, chưa phải deep analytics production.

### Douyin account/browser/extension/capture inbox

- Mục tiêu: kết nối local browser/extension, capture current page/profile, quản lý capture inbox.
- File chính: backend `douyin_accounts.py`, `douyin_extension.py`, `capture_inbox.py`; services `douyin_account_service.py`, `douyin_browser_connect_service.py`, `douyin_browser_context_registry.py`, `douyin_extension_capture_service.py`, `douyin_current_page_capture_service.py`, `capture_inbox_service.py`, `capture_metadata_normalizer.py`; web `douyin-extension-manager`, `capture-inbox`, `douyin-accounts`.
- Trạng thái: đã có nhiều route/service/test và docs phase logs. Browser-connect hiện có state machine/session model, Playwright capture path, persistent browser context registry và observability fields cho browser-primary fetch.
- Ghi chú: cần manual test với browser thật vì nhiều behavior phụ thuộc Douyin DOM/runtime/login/challenge. Không đọc cookie/token trong `.env` hoặc browser profile khi viết docs.

### Extension Phase 22C-9 đến 22C-9Z-3

- Mục tiêu: hardening Scan Profile state machine, DOM Probe sau ping, reuse legacy scanner, queue adapter, sửa watchdog stale timeout.
- File chính: `apps/extension-douyin-capture/src/background.ts`, `contentScript.ts`, `popup.ts`, `types.ts`, `wholeProfileHarvest/controller.ts`, `viewModel.ts`, tests liên quan.
- Trạng thái: Phase 22C-9Z-3 đã implement và validate bằng typecheck/test/build.
- Ghi chú quan trọng:
  - Current runtime version: `22C-9Z-3`.
  - Controller: `22C-9Z-3-scan-controller`.
  - Legacy message: `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`.
  - Queue adapter: `legacy_verified_target_queue_adapter_22C9Z3`.
  - Stale watchdog owner stage `resolving_tab` giờ bị guard nếu storage stage đã chuyển.

## 5. In-progress / Partially Completed Work

### Worker thực thi pipeline thật

Đã có local polling skeleton trong `apps/worker`, nhưng README ghi rõ chưa có crawler/OCR/STT/TTS/render/publish logic thật. Redis queue backend cũng chưa có.

### Real Douyin fetch/crawl

Backend có Douyin adapter, account-backed live fetch, browser-connect session/runtime và browser-primary fetch docs. Tuy vậy real success phụ thuộc browser profile đã login, Playwright/runtime local, Douyin challenge state và parser. Không nên mô tả đây là crawler tự động production-ready; execution path thực tế cần được xác minh qua `/intake` với connected account và observability fields `primary_execution_path`, `fetch_execution_path`, `final_execution_path_used`.

### Extension whole-profile harvest

Scan Profile Z3 vừa được sửa ở tầng route/watchdog/legacy invocation. Cần manual retest trên Douyin profile thật để xác nhận legacy scanner trả verified targets và queue count > 0 trong runtime thật.

### Publish connectors

Facebook Page/Reels connector và publish lifecycle foundation đã có, nhưng TikTok/YouTube connectors, production OAuth onboarding, scheduler thật và compliance automation vẫn ngoài scope hoặc chưa hoàn thiện.

### UI depth và data density

Web có nhiều màn hình ops/operator, nhưng mức polish khác nhau theo phase. Một số màn hình có thể là foundation/skeleton hoặc mock-backed; cần kiểm tra từng route trước khi chỉnh UX lớn.

## 6. Known Bugs / Issues / Risks

### Rủi ro: Extension Scan Profile phụ thuộc DOM Douyin thật

- Triệu chứng: scan có thể fail nếu Douyin đổi DOM, content script chưa inject, hoặc message handler không nhận.
- Nguyên nhân nghi ngờ: DOM selectors/runtime timing thay đổi; Chrome tab/page lifecycle; Douyin anti-bot/safety page.
- File liên quan: `contentScript.ts`, `modalWholeProfileTest.ts`, `background.ts`, `wholeProfileHarvest/controller.ts`.
- Hướng xử lý: manual retest trên nhiều profile; giữ diagnostics chi tiết; không thay `collectProfileCardsUntilStable(...)` internals nếu chưa audit kỹ.

### Rủi ro: Stale watchdog vừa sửa cần retest thủ công

- Triệu chứng cũ: `Last scanner error: scan_profile_stage_timeout:resolving_tab` dù DOM Probe đã found aweme IDs.
- Nguyên nhân cũ: timeout owner stage `resolving_tab` không kiểm tra current stage trước finalization.
- File liên quan: `apps/extension-douyin-capture/src/background.ts`.
- Hướng xử lý: reload extension, Scan Profile profile thật, kiểm tra `scan_stage_history`, `legacy_route_invoked`, `profile_queue_total_count`.

### Rủi ro: Một số provider/pipeline là placeholder

- Triệu chứng: output có thể là mock/placeholder thay vì media production thực.
- Nguyên nhân: README và docs nói audio/TTS/render foundations có placeholder/fallback providers.
- File liên quan: `apps/api/src/audio_pipeline`, `tts_pipeline`, `render_pipeline`, `downloaders/mock.py`, worker mock handlers.
- Hướng xử lý: xác định provider thật trước khi dùng production; viết integration tests với local assets.

### Rủi ro: Secrets/env không được audit trong handoff

- Triệu chứng: tài liệu thiếu chi tiết runtime config cụ thể.
- Nguyên nhân: theo yêu cầu không đọc/ghi secret trong `.env`.
- File liên quan: `.env.example` files only.
- Hướng xử lý: AI mới chỉ đọc `.env.example`; user tự cung cấp config nếu cần.

### Rủi ro: Repo có nhiều phase docs, có thể có docs cũ trái ngược code mới

- Triệu chứng: resume/log cũ nhắc Z1/Z2/Z-NOGIT hoặc pending validation; `docs/data-model-overview.md` vẫn có phần Current Limits cũ nói chưa có API/worker execution dù code hiện tại đã có nhiều route/service/job foundation.
- Nguyên nhân: phase logs theo thời gian, không phải tất cả được cập nhật khi phase mới hoàn thành.
- File liên quan: `docs/metadata-phase22C-*`, `docs/data-model-overview.md`, các docs browser/capture/publish theo phase.
- Hướng xử lý: ưu tiên code hiện tại, tests và docs phase mới nhất; dùng docs cũ để hiểu lịch sử, không coi là source of truth tuyệt đối.

### Rủi ro: Git/diff tooling từng lỗi trong session trước

- Triệu chứng: `git diff --stat` từng trả exit 129 với cảnh báo kiểu `--no-index`/pathspec.
- Nguyên nhân: chưa xác định, có thể do repo/env command parsing.
- File liên quan: không cụ thể.
- Hướng xử lý: dùng lệnh git đơn giản hơn hoặc PowerShell path quoting; không dùng destructive command.

### Rủi ro: Canonical capture metadata dễ lệch giữa extension/backend/frontend

- Triệu chứng: capture inbox/review board thiếu `posted_at`, counts, duration hoặc provenance; filter/score dùng field khác nhau giữa captured item và source video.
- Nguyên nhân: metadata được lấy từ nhiều nguồn (`network_json`, detail hydrate, DOM fallback) và phải merge theo identity ổn định.
- File liên quan: `docs/capture-metadata-canonical-contract.md`, `capture_metadata_normalizer.py`, `capture_inbox_service.py`, `apps/web/src/lib/captureInboxCanonical.ts`, extension extractor/detail hydration/network cache.
- Hướng xử lý: không merge bằng index; chỉ merge bằng `aweme_id`/external id; khi đổi field phải cập nhật contract, backend normalizer, frontend display/filter và tests.

## 7. Important Files and Responsibilities

| File/folder | Vai trò | Có nên chỉnh sửa không | Ghi chú khi chỉnh sửa |
|---|---|---:|---|
| `README.md` | Mô tả mục tiêu, architecture, Phase 1 scope | Có | Giữ đồng bộ với scope thực tế, không phóng đại production readiness |
| `docs/architecture-overview.md` | Tổng quan architecture và boundary | Có | Cập nhật khi thay đổi boundary lớn |
| `docs/metadata-phase22C-*` | Phase logs/resume của extension scanner | Có, cẩn thận | Dùng để trace lịch sử; docs cũ có thể stale |
| `docs/capture-metadata-canonical-contract.md` | Contract canonical metadata capture | Có | Source of truth cho `posted_at`, counts, duration, provenance, identity merge |
| `docs/douyin-browser-*-*.md` | Browser-connect/fetch/session docs | Có, cẩn thận | Nhiều file theo phase; ưu tiên architecture/user-guide mới và code hiện tại |
| `package.json` | Root workspace/scripts | Có, cẩn thận | Workspaces gồm web, extension, shared, config; API/worker Python không trong npm workspace |
| `apps/web/src/lib/api.ts` | Client API wrapper tập trung | Có | Khi đổi API contract phải cập nhật types/tests |
| `apps/web/src/lib/navigationConfig.ts` | Menu operator/ops | Có | Cập nhật i18n keys tương ứng |
| `apps/web/src/components/*` | UI modules theo domain | Có | Preserve existing visual/system patterns |
| `apps/web/src/types/*` | TypeScript contracts frontend | Có | Đồng bộ với backend schemas |
| `apps/api/src/main.py` | FastAPI app/router registration | Có | Nhớ include router mới |
| `apps/api/src/api/routes/*` | HTTP endpoints | Có | Không chạy long-running job inline |
| `apps/api/src/services/*` | Business/service layer | Có | Ưu tiên test service trực tiếp |
| `apps/api/src/services/douyin_browser_connect_service.py` | Local Playwright/browser login session capture, account session validation/state | Có, cẩn thận | Phụ thuộc runtime/browser thật; không log secrets/cookies |
| `apps/api/src/services/capture_inbox_service.py` | Capture session/items, metadata normalization, promotion to candidates/reup queue | Có, rất cẩn thận | Schema rộng; chạy capture inbox/API tests khi đổi |
| `apps/api/src/services/export_handoff_service.py` | Export package/publish handoff từ reup queue | Có | Đồng bộ web `export-handoff.ts` và publish handoff UI |
| `apps/api/src/models/*` | SQLAlchemy models | Có, rất cẩn thận | Cần Alembic migration khi đổi schema |
| `apps/api/src/schemas/*` | Pydantic API schemas | Có | Cập nhật tests/frontend types nếu đổi field |
| `apps/api/alembic/versions/*` | DB migrations | Có, cẩn thận | Không sửa migration đã áp dụng nếu không hiểu trạng thái DB |
| `apps/worker/src/runtime.py` | Local polling worker skeleton | Có | Hiện chưa phải queue production |
| `apps/extension-douyin-capture/src/background.ts` | Background service worker, CDP, Scan Profile watchdog/runtime | Có, rất cẩn thận | Recent Z3 watchdog fix nằm ở đây; test extension sau mọi sửa |
| `apps/extension-douyin-capture/src/contentScript.ts` | DOM/page context, scanner message handlers, harvest runtime | Có, rất cẩn thận | Chạy trong trang Douyin; tránh secret/token capture |
| `apps/extension-douyin-capture/src/popup.ts` | Popup UI/controller lớn | Có, cẩn thận | File rất lớn; chỉnh surgical, chạy typecheck/test |
| `apps/extension-douyin-capture/src/modalWholeProfileTest.ts` | Legacy verified profile scanner | Không nếu không bắt buộc | User trước đó cấm chỉnh internals trừ diagnostics harmless |
| `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts` | Main whole-profile workflows/state transitions | Có, rất cẩn thận | Nhiều flow: scan, verify, collect, flush, reset |
| `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts` | Chrome storage state model/normalization | Có, cẩn thận | Migration/normalization impact lớn |
| `apps/extension-douyin-capture/src/types.ts` | Extension message/response contracts | Có | Message literal phải đồng bộ background/contentScript/tests |
| `apps/extension-douyin-capture/src/*test.ts` | Extension regression tests | Có | Nên thêm test khi đổi scanner state machine |
| `.env`, `.env.local` | Secrets/local config | Không đọc/ghi trong handoff | Chỉ dùng `.env.example` khi cần docs |

## 8. Data Models / State / API Contracts

### Backend models/schemas

Các SQLAlchemy models nằm trong `apps/api/src/models`:

- `foundation.py`: workspace/base domain.
- `ingestion.py`, `source_accounts.py`, `intake.py`: source/profile/crawl/intake.
- `jobs.py`: durable job and steps.
- `media.py`: media assets/storage manifests.
- `review.py`, `reup_queue.py`: candidate review/reup queue.
- `artifacts.py`: transcript/translation/editable AI artifacts.
- `publish.py`, `analytics.py`, `export_handoff.py`, `capture_inbox.py`: publish/capture/analytics/export domains.

Pydantic schemas nằm trong `apps/api/src/schemas`, thường mirror route domains. Khi đổi response/request, cập nhật frontend `apps/web/src/types/*` và tests tương ứng.

### Frontend types/state

Frontend type contracts nằm trong `apps/web/src/types`. State helpers nằm trong `apps/web/src/lib/*State.ts`, ví dụ:

- `reviewBoardState.ts`, `reviewCandidateMetadata.ts`.
- `intakeState.ts`.
- `transcriptEditorState.ts`, `finalReviewState.ts`.
- `publishDraftState.ts`, `publishControlState.ts`, `publishHealthState.ts`.
- `captureInboxCanonical.ts`, `captureInboxFilterMetadata.ts`, `captureInboxReupScore.ts`.
- `operatorHomeState.ts`, `optimizationState.ts`, `riskState.ts`.

### Canonical capture metadata contract

Contract quan trọng nằm ở `docs/capture-metadata-canonical-contract.md`. Các field canonical cần giữ đồng bộ extension -> backend -> web:

- Identity: dùng `aweme_id`/external id ổn định; không merge item theo index grid.
- Time/counts: `posted_at`, `posted_text`, `view_count`, `like_count`, `comment_count`, `share_count`.
- Derived/display: `engagement_rate`, `duration_seconds`, `thumbnail_source`, provenance metric-level nếu có.
- Processing-fit/risk fields: `has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`.
- Source priority: network/detail hydrate thường ưu tiên hơn DOM fallback; nếu thiếu thì giữ null/provenance thay vì tự bịa.

### Browser-connect/account state

Models/services liên quan nằm ở `source_accounts.py`, `douyin_account_service.py`, `douyin_browser_connect_service.py`, `douyin_browser_context_registry.py`. Browser-connect có session statuses (`pending`, `launching_browser`, `waiting_for_login`, `capturing_session`, `validating`, ...), health/connection status cho account và metadata runtime browser profile. Browser-primary fetch contract cần expose observability fields để operator biết đang dùng browser profile hay HTTP fallback.

### Extension message contracts

`apps/extension-douyin-capture/src/types.ts` định nghĩa `ExtensionMessage` và `ExtensionMessageResponse`. Message quan trọng hiện tại:

- `DOUYIN_SCANNER_PING` / `REUP_DOUYIN_PING`.
- `DOUYIN_PROFILE_DOM_PROBE`, `DOUYIN_PROFILE_DOM_PROBE_22C9H`, `DOUYIN_PROFILE_DOM_PROBE_22C9I`.
- `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3`.
- `REUP_DOUYIN_CAPTURE`, harvest V2 messages, calibration messages.

### Extension whole-profile state

Whole-profile harvest state nằm trong `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`. State gồm phase, calibration, classification, harvest queue, results, debug diagnostics, safety pause, backend session, traces.

Z3 diagnostics quan trọng cần biết:

- Version: `22C-9Z-3`, controller `22C-9Z-3-scan-controller`.
- Run id prefix: `scan_profile_22C9Z3_`.
- Stage fields: `scan_stage_current`, `scan_stage_previous`, `scan_stage_history`, `scan_stage_updated_at`.
- Watchdog fields: `scan_watchdog_id`, `scan_watchdog_active_stage`, `scan_timeout_owner_stage`, `scan_timeout_ignored_reason`.
- Legacy scanner fields: `legacy_route_invoked`, `legacy_scanner_route_invoked`, `legacy_scanner_invocation_result`, `legacy_scanner_message_type`.
- Queue adapter fields: `scan_queue_builder_used`, `legacy_queue_adapter_result`, `legacy_queue_adapter_output_count`, `profile_queue_total_count`.

## 9. UI/UX Status

### Screens hiện có

Operator side:

- `/` operator home.
- `/intake`, `/intake/profiles`, `/intake/crawl-sessions`.
- `/accounts/douyin`.
- `/setup/douyin-extension`.
- `/selection/review-board`, `/selection/candidates`, `/review-board`.
- `/selection/reup-queue`.
- `/source-videos/[id]/transcript-editor` and `/production/transcript-editor/[sourceVideoId]`.
- `/source-videos/[id]/final-review` and `/production/final-review/[sourceVideoId]`.
- `/source-videos/[id]/publish`, `/publishing/drafts`, export packages, publish handoffs.
- `/optimization`, `/publish-control`.

Ops side:

- `/ops`, `/ops/health`, `/ops/jobs`, `/ops/pipeline`, `/ops/assets`.
- `/publishing/accounts`, `/ops/routing-rules`, `/ops/publish-control`, `/ops/publish-health`, `/ops/publish-attempts`, `/ops/reconciliation`.
- `/ops/risk`, `/ops/optimization`, `/ops/tools`.
- `/ops/extensions/douyin` (legacy redirect), `/selection/capture-inbox` (Capture Inbox; legacy `/ops/extensions/douyin/capture-inbox` redirects).

### UI status

- Review board, transcript editor, final review, publish draft are described as available foundations.
- Capture inbox and Douyin extension manager have dedicated components/tests and multiple design phase docs.
- Ops console appears broad but may contain foundation/mock-backed summaries depending on endpoint/data availability.
- Existing app uses established component folders and i18n; preserve current design system instead of introducing unrelated visual style.

### UX risks

- Some screens may be dense due to operator/ops diagnostics.
- Some nav items are context-dependent and require selected source video.
- Data availability depends heavily on seeded DB, backend running, extension capture sessions, and local storage assets.
- Need check mobile responsiveness route-by-route; primary operator likely desktop Windows.

## 10. Testing Status

### Existing tests

Root:

- `npm run test` maps to PowerShell smoke check.
- `npm run typecheck` runs web typecheck.
- `npm run extension:test` runs extension tests.

Web:

- Script: `npm --workspace @reup-douyin/web run test`.
- Tests include review board, transcript editor, final review, publish draft, risk, publish health/control, optimization, intake, operator home, Douyin extension install/manager UX, pipeline dashboard, route nav, capture inbox.

API:

- Tests in `apps/api/tests` cover job state machine/progress, adapters, candidate scoring, audio/TTS/render pipeline, publish lifecycle/reconciliation/routing/health, risk policy, storage manifest, Douyin account/browser/extension/capture inbox services, intake, reup queue, review board delete.
- Likely run with pytest from `apps/api` after Python deps/env configured. Cần kiểm tra thêm exact command trong local scripts nếu environment mới.

Extension:

- Script: `npm --workspace @reup-douyin/extension-douyin-capture run test`.
- Covers extractor, network cache, CDP aweme, modal harvest, background, popup workflows/progress/transport, reset, harvest runtime V2, backend client, wholeProfileHarvest calibration/readiness/viewModel/backendFlow/queue/tabs/wording/hardening/controller, UI command shell.
- Recent Z3 validation passed:
  - `npm run -w apps/extension-douyin-capture typecheck`
  - `npm run -w apps/extension-douyin-capture test`
  - `npm run -w apps/extension-douyin-capture build`
  - stale string scan found no `22C-9Z-2` or `22C9Z2` in searched extension source paths.

### Run/build commands

Local full dev helper scripts:

```powershell
.\scripts\dev-doctor.ps1
.\scripts\dev-migrate.ps1
.\scripts\dev-reseed.ps1
.\scripts\dev-start.ps1
```

Root npm:

```powershell
npm run doctor
npm run db:migrate
npm run dev:reseed
npm run dev
npm run dev:stop
```

Web:

```powershell
npm --workspace @reup-douyin/web run typecheck
npm --workspace @reup-douyin/web run build
npm --workspace @reup-douyin/web run test
```

Extension:

```powershell
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run build
npm --workspace @reup-douyin/extension-douyin-capture run package
```

API/worker:

```powershell
# from apps/api, after deps/env
pytest

# from apps/worker, after deps/env
python src/main.py
```

### Manual tests quan trọng

- Web smoke: start API + web, open operator home, review board, intake, capture inbox, transcript editor/final review with seeded data.
- Backend smoke: run migrations, seed demo, hit `/ops/metrics`, key list endpoints.
- Extension Scan Profile Z3: reload unpacked extension from `apps/extension-douyin-capture/dist`, open Douyin profile, click Scan Profile, inspect diagnostics for Z3, legacy invocation, queue count.
- Capture inbox: capture item/session from extension, verify backend stores and web displays item.

## 11. Recommended Next Steps

### P0 - bắt buộc xử lý ngay

1. Manual retest extension Scan Profile Z3 trên Douyin profile thật: reload unpacked extension từ `dist`, mở profile có grid public, bấm Scan Profile, copy debug JSON và xác nhận `scan_stage_history` đi qua `probing_dom` -> `legacy_scanner_invocation`, không còn stale `scan_profile_stage_timeout:resolving_tab`, `legacy_route_invoked=yes`, `legacy_scanner_invocation_result=success`, `profile_queue_total_count > 0`.
2. Nếu Z3 vẫn fail, lấy `douyinWholeProfileHarvestState.debug.last_request_summary`, `last_response_summary`, `scan_watchdog_id`, `scan_timeout_owner_stage`, `legacy_scanner_message_type`, Chrome runtime errors; không sửa scanner internals trước khi audit owner/stage/message path.
3. Chạy lại extension test/typecheck/build sau bất kỳ sửa nào trong `background.ts`, `contentScript.ts`, `controller.ts`, `types.ts`, `popup.ts`.
4. Retest capture metadata canonical path: capture một profile/video có counts + posted time, kiểm tra backend captured item và web capture inbox hiển thị cùng canonical fields theo `docs/capture-metadata-canonical-contract.md`.

### P1 - quan trọng

1. Tạo/update phase log chính thức cho `22C-9Z-3` trong `docs/metadata-phase22C-*` vì hiện docs mới nhất chỉ có Z-NOGIT/Z1-ish; handoff này ghi nhận Z3 nhưng phase doc riêng cần kiểm tra thêm.
2. Kiểm tra end-to-end capture inbox: extension capture -> backend `capture_sessions`/`captured_items` -> web `/selection/capture-inbox` -> promote sang candidate/reup queue; chạy liên quan `test_douyin_extension_capture_service.py`, `test_capture_inbox*` nếu có deps.
3. Xác nhận browser-connect/intake thật: connected account -> browser-primary `/intake` discovery -> observability fields `primary_execution_path=browser_profile`/fallback reason -> persisted crawl/source video.
4. Xác nhận backend/web smoke trên DB local mới sau migrations và seed.
5. Rà soát các màn hình ops/operator có data thật hay skeleton/mock để đánh dấu rõ trong docs/UI.

### P2 - cải thiện sau

1. Chuẩn hóa docs phase cũ để giảm nhầm lẫn Z1/Z2/Z3.
2. Tách bớt `popup.ts` nếu có phase refactor an toàn; hiện file rất lớn và rủi ro khi sửa.
3. Nâng worker từ mock/local polling skeleton sang handler thật cho một pipeline nhỏ có idempotency/retry rõ.
4. Thêm integration tests cho web/API contracts hoặc generate shared contract để giảm lệch schema TypeScript/Pydantic.
5. Polish UX/data density cho capture inbox, review board, ops console sau khi flow dữ liệu ổn định.

## 12. Prompt for New AI Conversation

Bạn là coding agent tiếp tục project `reup-douyin` trong repo local. Đây là monorepo local-first cho operator Windows reup nội dung Douyin: `apps/web` là Next.js UI, `apps/api` là FastAPI + SQLAlchemy backend, `apps/worker` là polling worker skeleton, `apps/extension-douyin-capture` là Chrome extension capture/scan Douyin. Hãy đọc `docs/PROJECT_CONTEXT_HANDOFF.md`, `README.md`, `docs/architecture-overview.md`, `docs/capture-metadata-canonical-contract.md`, các docs `douyin-browser-*` liên quan, và file code trực tiếp trước khi sửa vì nhiều phase docs cũ có thể stale. Không đọc/ghi secret trong `.env`, cookie, token hoặc browser profile. Gần nhất đã hoàn thành extension Phase `22C-9Z-3`: sửa stale Scan Profile watchdog ở `background.ts`, ép legacy scanner `DOUYIN_RUN_LEGACY_PROFILE_SCROLL_SCAN_22C9Z3` sau DOM Probe productive, dùng queue adapter `legacy_verified_target_queue_adapter_22C9Z3`, typecheck/test/build extension đã pass. Việc ưu tiên tiếp theo là manual retest Scan Profile trên Douyin thật, retest canonical capture metadata/capture inbox, và xác minh browser-primary intake với connected account. Khi sửa extension, chỉnh surgical và chạy `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`, `test`, `build`. Khi sửa web/API, đồng bộ schemas/types/tests và giữ boundary: web không crawl/process, API không chạy long-running inline, worker xử lý job dài hạn.
