# Handoff: Extension Hybrid Collect (Phase 4)

**Cập nhật lần cuối:** 2026-07-11 — Scan → Collect operator path ổn định; presentation/revisit fixes; collected-profile reopen.

**Đọc file này + `RULE.md` ở đầu mỗi phiên chat mới** khi tiếp tục extension Douyin capture / Hybrid collect / tile UI / Capture Inbox thumbnail.

| | |
|---|---|
| **Scope** | Chủ yếu `apps/extension-douyin-capture`; thumbnail còn `apps/api`, `apps/web` |
| **Rule** | `RULE.md` + `.cursor/rules/diagnose-before-fix.mdc` |
| **Flag** | `chrome.storage.local.hybrid_network_cache_mode === true` |
| **Luồng** | Scan → (Calibrate 4P *chỉ modal*) → Start Collecting → `runBatchCollectHybridNetworkCacheMode` → full-modal-harvest → Capture Inbox |

Sau mỗi sửa extension: **Reload** trên `chrome://extensions`. Sau sửa API/web thumbnail: **restart API** + hard refresh Capture Inbox.

### Tóm tắt phiên 2026-07-11

- **Operator:** Luồng **Scan Profile → Collecting Videos** ổn định trên máy operator (happy path).
- **Xong (presentation / revisit):** Revisit profile không còn kẹt **Scan Profile** khi scan đã complete; Hybrid ON không còn ép **Calibrate 4P** sau rescan; giảm flicker scan/rescan; rescan loop khi queue đủ nhưng `scan_job.status=failed`; profile đã collect xong (143/143) + mismatch session → **Open Capture Inbox** thay **Rescan profile**.
- **Build extension mới nhất:** `reup-douyin-extension-2026-07-11T05-40-43-156Z`
- **Chưa đóng Phase 4:** 4.5 (checkpoint resume), 4.7–4.9 (coverage doc); `hybridRunnerIdempotency.test.ts` vẫn fail 1 case; pre-skip inflate batch 2 chưa re-verify formal.

### Tóm tắt phiên 2026-07-08 (giữ lịch sử)

- **Xong:** Thumbnail Capture Inbox (proxy API, test PASS). Pre-skip batch 2: không false-complete khi `snapshot.new > 0` + `pending=0`.

---

## Phase 4 — trạng thái (2026-07-11)

| Phase | Trạng thái | Ghi chú |
|---|---|---|
| 4.1–4.3 | ✅ | Whitelist runner, routing, flag |
| 4.4a–4.4d | ✅ | Target → hydrate → per-item / loop flush |
| 4.4e | ✅ | Hydrate all → flush chunks ≤500; fossil `flush_mode/chunk_*` |
| 4.4f | ✅ | `PerItemFlushRecord` / fossil per-item (`p`, `src`) |
| 4.5 | ⚠️ | Heartbeat merge-only; **chưa** cursor checkpoint resume đầy đủ |
| 4.6 | ✅ | Auth pause 401/403 + logout UX |
| 4.7–4.9 | ⚠️ | Có idempotency + hydration proof tests; **chưa** doc coverage %; 1 idempotency test fail |

**Bất biến:** exact `aweme_id`; `estimated_views` ≠ `view_count`; thiếu required field → `skipped_pending`, không modal-fallback.

**Required metrics:** `duration_seconds`, `like_count`, `comment_count`, `favorite_count` (`collect_count`), `share_count`, `thumbnail`, `posted_at`.

---

## Đã làm — phiên 2026-07-10/11 (presentation & revisit)

### Revisit profile — stale Scan CTA (Bug A)

**Triệu chứng:** Scan nhiều profile, quay lại profile cũ → UI 143/143 ready nhưng CTA vẫn **Scan Profile**.

**Root cause:** `workflow.scan.status` kẹt `"running"` → `collectPresentationSuppressed()` chặn collect routing.

**Fix:** `profileContext.ts` — terminal scan complete không suppress; `readiness.ts` — `scanRoutingPresentationComplete`, `hasActionableCollectWork` cho empty queue + persisted totals.

**Tests:** `activeProfilePresentation.test.ts`, `wholeProfileHarvest.profileContext.test.ts`.

### Hybrid ON → Calibrate sau rescan (Bug B)

**Triệu chứng:** Scan lần 2+ → **Calibrate 4 Points** + **Cal needed** dù đã bật Hybrid.

**Root cause:** `runScanProfileWorkflow` ghi đè `last_response_summary` → mất `hybrid_network_cache_mode_flag`; popup không hydrate hybrid từ `chrome.storage`.

**Fix:** `readiness.ts` — `preserveOperatorCollectPrerequisitesInDiagnostics()`, `readHybridNetworkCacheModeFlagFromState()`; `controller.ts` hydrate + preserve on finalize; `popup.ts` apply hybrid từ storage on runtime message.

### Scan / rescan UX flicker

**Fix:** `shouldHoldScanPresentationForRescan()`; `buildVerifyProfileScanBootstrapState()` preserve snapshot on rescan; popup optimistic scan giữ snapshot; terminal render immediate; skip context refresh during scan.

### Rescan loop (queue 366, scan_job failed)

**Triệu chứng:** Queue/ready đủ nhưng CTA kẹt **Rescan profile** + "Scan didn't finish".

**Fix:** `scanQueueProvesSessionCompleteForPresentation()`, `harvestQueueActionableCountForPresentation()`; `scanBlocksCollectPresentation` không block khi persisted meets expected / queue proves complete.

**Tests:** `wholeProfileHarvest.scanPresentationPhase.test.ts`, `viewModel.test.ts`.

### Collected profile reopen (143/143 + Different profile banner)

**Triệu chứng:** Profile đã collect xong, backend có data → banner **Different profile**, CTA **Rescan profile**, **Cal needed**.

**Root cause:** `revisit_mismatch` + profile context gate luôn ép Rescan; chưa xử lý inbox complete trên active tab.

**Fix:**

- `activeProfilePresentation.ts` — inbox complete → **Open Capture Inbox**, tiles 0 new/queue.
- `profileContext.ts` — banner inbox complete.
- `viewModel.ts` — gate mismatch + inbox complete → `open_capture_inbox`; ẩn **Cal needed**.

**Tests:** `activeProfilePresentation.test.ts` (case 143 collected).

### Build IDs (phiên 2026-07-11)

| Build | Nội dung |
|---|---|
| `reup-douyin-extension-2026-07-11T04-04-27-328Z` | Hybrid flag preserve |
| `reup-douyin-extension-2026-07-11T04-57-11-220Z` | UX smoothing (scan flicker) |
| `reup-douyin-extension-2026-07-11T05-15-49-432Z` | Rescan loop fix |
| `reup-douyin-extension-2026-07-11T05-38-04-155Z` | Collected profile reopen |
| `reup-douyin-extension-2026-07-11T05-40-43-156Z` | **Mới nhất** (sau doc sync) |

---

## Đã làm (tích lũy qua các phiên trước)

### Backend / runner (`controller.ts`, `hybridHydration.ts`, …)

- **Pre-skip + drain:** scan tối đa 500 actionable, reconcile hết, bỏ throttle Next-10 modal; mỗi click drain tới 500.
- **Chunked flush (4.4e):** hydrate all → flush theo chunk ≤500; fossil `hybrid_runner_flush_mode=chunked`.
- **Tile authority:** `refreshHybridTilesFromCaptureInboxCard`, floor `hybrid_profile_collected_floor`, reconcile `write_ok` dùng `max(newlyAdded, matchedQueueCount)`.
- **Stale-write guard:** `writeHybridLoopHeartbeat` (merge-only); monotonic `post_scan_counter_snapshot`; `hybrid_collection_done` mang `tile_*` + `applyHybridCollectionDoneOverride`.
- **Skipped_pending fixes:** `favorite_count` từ `collect_count`; `duration_seconds` từ ms/text/image-post; thumbnail protocol-relative + thử mọi cover candidate.
- **Large profile:** scan persist metrics vào `profile_card_evidence` (`contentScript.ts`); compaction giữ metrics (`background.ts`); pending query **offset=0** (không dùng `collect_cursor` làm offset pending).
- **Batch ưu tiên:** chọn `metricsReadyTargets` trước (`evidenceHasHybridRequiredMetrics`).
- **Auto-skip:** batch toàn `skipped_pending` → `markHybridMetricsMissingTargetsAsSkipped` → unlock + fossil `uncollectable_skipped_count`.

### Calibration (Hybrid ON)

- **Bỏ gate Calibrate 4 Points** — `isCollectCalibrationSatisfied` trong `readiness.ts`; preflight `calibration_skipped_for_hybrid=yes`. Modal (flag OFF) vẫn bắt calibrate.
- **Bổ sung 2026-07-11:** preserve hybrid flag qua scan finalize + popup hydrate (xem Bug B).

### UI/UX + Skip incomplete (`viewModel.ts`, `popup.ts`, `hybridMetricsMiss.ts`)

- Action `skip_hybrid_incomplete`; `runSkipHybridUncollectableRemainder()`; background dispatch `DOUYIN_SCANNER_SKIP_HYBRID_INCOMPLETE`.
- **Trạng thái:** code ✅; **runtime operator chưa ghi nhận** formal sau build 2026-07-11.

### Start Collecting sau backend wipe + delay UI

- Stale/reconcile/quota/delay fixes đã merge (phiên 2026-07-05/06).
- **Operator 2026-07-11:** happy path Scan → Collect ổn định; chưa có log fossil mới cho wipe scenario.

### Thumbnail Capture Inbox + backend collect authority (phiên 2026-07-07/08)

- **Thumbnail:** API public_router proxy + signed URL + web `resolveThumbnailDisplayUrl` — test PASS.
- **Backend collect authority:** `backendCollectAuthority.ts`, profile-scoped verify — test PASS.
- **Pre-skip inflate:** log operator `pre_skip_already_collected: 468` khi backend `500` — **chưa re-verify** sau build 2026-07-11; có thể vẫn fail trên profile >500 batch 2.

---

## File chạm chính

| File | Vai trò |
|---|---|
| `wholeProfileHarvest/controller.ts` | Runner, heartbeat, reconcile, tile, hybrid flag preserve on scan |
| `wholeProfileHarvest/readiness.ts` | Calibration skip, hybrid flag, `preserveOperatorCollectPrerequisitesInDiagnostics` |
| `wholeProfileHarvest/profileContext.ts` | Mismatch, revisit, `shouldHoldScanPresentationForRescan`, `scanQueueProvesSessionCompleteForPresentation` |
| `wholeProfileHarvest/activeProfilePresentation.ts` | Revisit mismatch presentation; inbox complete → Open Capture Inbox |
| `wholeProfileHarvest/viewModel.ts` | Panel VM, profile context gate, `scanBlocksCollectPresentation` |
| `wholeProfileHarvest/scanPresentationPhase.ts` | Scan phase → complete khi queue proves session |
| `wholeProfileHarvest/hybridMetricsMiss.ts` | Metrics-miss detect + Skip UI |
| `wholeProfileHarvest/backendCollectAuthority.ts` | Backend authority cho captured count |
| `popup.ts` | Optimistic scan/collect, hybrid hydrate, terminal render |
| `background.ts` | Runner whitelist, skip hybrid dispatch |
| `apps/api/.../capture_inbox.py` | Thumbnail public_router |
| `apps/web/.../captureInboxCanonical.ts` | Thumbnail proxy resolver |

**Tests (chạy sau sửa extension):**

```bash
npm --workspace @reup-douyin/extension-douyin-capture run build

# Core hybrid + presentation
npx tsx src/wholeProfileHarvest.readiness.test.ts
npx tsx src/wholeProfileHarvest.profileContext.test.ts
npx tsx src/activeProfilePresentation.test.ts
npx tsx src/wholeProfileHarvest.scanPresentationPhase.test.ts
npx tsx src/wholeProfileHarvest/viewModel.test.ts

# Hybrid runner (1 case vẫn fail — xem Dang dở)
npx tsx src/wholeProfileHarvest.hybridRunnerIdempotency.test.ts

# Regression
npx tsx src/wholeProfileHarvest.test.ts
npx tsx src/wholeProfileHarvest.operatorRegression.test.ts
npx tsx src/backendCollectAuthority.test.ts
npx tsx src/hybridHydration.proof.test.ts

# Thumbnail (API + web)
cd apps/api && python -m unittest tests.test_capture_inbox_thumbnail_proxy -v
cd apps/web && npx tsx src/test/capture-inbox-canonical.test.ts
```

**Known test debt:** `popupWorkflow.test.ts` fail pre-existing (line ~462, unrelated presentation fixes).

---

## Cần xác nhận runtime (operator)

Profile **đã scan trước khi có fix metrics** → nên **Scan lại** rồi Collect.

### Checklist happy path (ưu tiên — operator đã PASS 2026-07-11)

1. Hybrid ON → Scan Profile → Start Collecting (không Calibrate 4P).
2. Collect xong → tile **Already** khớp Capture Inbox; CTA **Open Capture Inbox**.
3. Quay lại profile đã scan → **Start Collecting** hoặc **Open Capture Inbox** (không kẹt Scan Profile / Rescan loop).
4. Profile đã collect 100% + session profile khác → **Open Capture Inbox**, không **Rescan** + **Cal needed**.

### Checklist còn lại (chưa ghi nhận PASS formal)

1. **Thumbnail:** restart API → Capture Inbox thumbnail 200 (không 401).
2. **Skip N incomplete:** profile 997/999, Queue=2 → Skip → Queue=0 → Open Capture Inbox.
3. **Batch 2 / pre-skip:** profile >500, batch 2 — `post_run_backend_captured` tăng thật; `pre_skip_already_collected` không inflate.
4. **Start Collecting sau wipe:** UI phản hồi <2s; `write_ok_count` tăng thật.
5. **Fossil 4.4e:** `hybrid_runner_flush_mode=chunked` trên profile lớn.

---

## Việc tiếp theo (ưu tiên 2026-07-11)

### A — Chuyển sang pipeline sản phẩm (khuyến nghị nếu Scan→Collect ổn)

1. Capture Inbox audit (`/ops/extensions/douyin/capture-inbox`) — 143 item, metadata đủ.
2. **Promote** 5–10 ready → Review Board.
3. Pilot light load theo `docs/operator-pilot-workflow.md`.

### B — Đóng Phase 4 extension (khi pilot báo lỗi hoặc chủ động harden)

1. **Re-verify pre-skip inflate** trên profile >500 batch 2; fix `verifyHybridProfileCapturedAwemeIds` nếu tái hiện.
2. **Fix** `hybridRunnerIdempotency.test.ts` — `testSecondRunSkipsAlreadyCollectedAndFlushesNextBatch` (expected 12, got 0).
3. **Runtime verify** thumbnail, Skip incomplete, wipe scenario.
4. **Phase 4.5** — cursor checkpoint resume giữa chừng.
5. **Phase 4.7–4.9** — test hydrate đầy đủ + doc coverage %.

**Non-goals:** crawler mới, scoring, auto-publish, đổi public API contract ngoài extension collect + thumbnail proxy.

---

## Dang dở (cập nhật 2026-07-11)

| Hạng mục | Trạng thái |
|---|---|
| Scan → Collect happy path (operator) | ✅ Ổn định (2026-07-11) |
| Revisit / rescan / hybrid presentation fixes | ✅ Code + test PASS |
| Collected profile reopen (inbox complete) | ✅ Code + test PASS |
| Thumbnail — code + test | ✅ Test PASS; **runtime chưa ghi nhận** |
| Pre-skip inflate (batch 2, profile >500) | ⚠️ Chưa re-verify sau build 2026-07-11 |
| Skip incomplete — runtime operator | ❌ Chưa xác nhận |
| Start Collecting sau wipe — runtime | ⚠️ Chưa xác nhận formal |
| `hybridRunnerIdempotency.test.ts` | ❌ Fail `testSecondRunSkipsAlreadyCollectedAndFlushesNextBatch` |
| `popupWorkflow.test.ts` | ❌ Fail pre-existing (~line 462) |
| Phase 4.5 checkpoint resume | ❌ Chưa làm |
| Phase 4.7–4.9 coverage doc | ⚠️ Một phần |

---

## Prompt phiên mới

```
Đọc docs/handoff-hybrid-collect-phase4.md và RULE.md.
Tiếp tục: [mô tả việc].
Log: [dán hybrid_runner_* / per_item_summary / service worker console].
Build hiện tại: reup-douyin-extension-2026-07-11T05-40-43-156Z
```

**Gợi ý tiếp tục ngắn:** Capture Inbox → Promote → Review Board pilot; hoặc re-verify pre-skip batch 2; fix idempotency test; Phase 4.5.
