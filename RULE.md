# Diagnose-Before-Act (project rule)

Áp dụng cho **mọi nhiệm vụ** trong repo — bug, UX/UI, feature, phase, refactor, test, docs, review, tối ưu, hỏi đáp.

**Mỗi lần đưa phương án / giải pháp cho user:** bắt buộc theo workflow và **template đề xuất** ở cuối file (trừ câu hỏi yes/no đơn giản không liên quan code).

Chi tiết Cursor: `.cursor/rules/diagnose-before-fix.mdc`, `root-cause-proposal.mdc`, `test-before-code-change.mdc`.

---

## Workflow bắt buộc

### 1. Thu thập bằng chứng (trước khi đề xuất hoặc sửa)

- **Mô tả user** + **ngữ cảnh chat** (phase, quyết định đã khóa, ràng buộc).
- **Ảnh / video UI/UX** (nếu có): ghi nhận trạng thái hiển thị, CTA, counter, badge, copy — so với kỳ vọng operator.
- **Log / fossil / API response / error code** (nếu có).
- **Đọc code** — không đoán từ trí nhớ:
  - **Luồng chính:** entry, authority / source of truth, state write, contract public.
  - **Luồng liên quan:** caller, consumer, test, invariant kề (vd. tile vs backend, auth vs `<img>`, extension vs API).

Khoanh vùng rõ: app/package, route, file/hàm, tầng (web / api / worker / extension).

### 2. Chẩn đoán — một vấn đề gốc

- **Một** root cause có bằng chứng; tách triệu chứng phụ — không gộp mơ hồ.
- Chỉ rõ **chokepoint** (điểm sửa tối thiểu, tác động tối đa).

### 3. Đề xuất phương án (trước khi sửa code)

User chưa bảo implement / fix / OK → **chỉ đề xuất**, dùng **template đề xuất** bên dưới.

Phương án phải đạt **tiêu chí chất lượng** (mục tiếp theo). Một phương án triệt để tại chokepoint — không vá rải rác, không nhảy phase.

### 4. Test trước, sửa sau (hành vi / bug)

Theo `.cursor/rules/test-before-code-change.mdc`:

- Test mô tả hành vi đúng hoặc tái hiện bug → **chạy trước** khi sửa production.
- Bug: test **FAIL** trước → fix → **PASS**.
- Ngoại lệ: docs/copy thuần; user skip test; task chỉ đọc/hỏi/review.

### 5. PASS và hoàn tất

- Checklist PASS cụ thể, quan sát được (UI, API, log, test, build).
- Làm đến khi đạt PASS — không dừng ở “có vẻ ổn” hoặc chỉ typecheck khi task là hành vi.

### 6. Tối ưu phạm vi

- Ưu tiên 1–3 file / chokepoint; ít đọc thừa, ít vòng sửa.
- Không mở rộng scope; phase sau để phase sau. Tôn trọng `AGENTS.md`.

---

## Tiêu chí chất lượng đề xuất & code

Góc nhìn operator + chuẩn kỹ thuật repo. Mỗi đề xuất fix phải đề cập các mục **áp dụng được** (không liệt kê cho có).

| Tiêu chí | Ý nghĩa |
|----------|---------|
| **Backend đúng** | API/worker chạy được; contract ổn định; lỗi có mã + message hành động được. |
| **UI khớp backend** | Màn hình đọc **cùng authority** với API (không hai nguồn truth — vd. canonical resolver vs `*_status` lệch nhau). Số, label, CTA phản ánh state thật. |
| **Nhánh có chủ đích** | Liệt kê **ma trận trạng thái** quan sát được (empty / loading / success / partial / failed / unauthorized…) và xử lý tại chokepoint — không spam if-else cho case không thể xảy ra theo code. |
| **Ít code thừa / xung đột** | Diff nhỏ; không trùng logic đã có; không phá invariant (counter, idempotent, canonical flow). |
| **Bảo mật** | Không lộ secret/token/path nhạy cảm; validate input; auth đúng tầng; fail-closed; không mở endpoint/public surface không cần thiết. |
| **Bảo trì / mở rộng** | Tên rõ, type rõ, tái dùng helper có sẵn; infrastructure tách product workflow (`AGENTS.md`). |
| **Quan sát được** | Log lifecycle có id ổn định; dễ debug operator. |
| **Test khi đổi hành vi** | Contract test gần code đổi; mock I/O ngoài (Douyin, CDN) trong test mặc định. |

**Anti-pattern:** vá copy/UI che triệu chứng khi authority sai; hardcode path user-specific; commit secrets; scatter-shot nhiều file.

---

## Áp dụng theo loại task

| Loại | Trọng tâm | PASS ví dụ |
|------|-----------|------------|
| Bug / UX sai | Root cause + UI vs backend | Tái hiện hết; test regression; UI khớp API |
| Feature / phase | Boundary hiện có + phase doc | Hành vi mới PASS; không phá luồng cũ |
| Review / hỏi đáp | Đọc code thật + citation | Trả lời đúng implementation hiện tại |
| Docs / rule | Khớp repo | Không ghi “đã xong” capability chưa có |

---

## Template đề xuất (bắt buộc khi đưa phương án)

Dùng format này **mỗi khi** đề xuất fix / thiết kế / tối ưu (trước khi implement, trừ khi user đã bảo làm ngay):

```
## Bằng chứng
- Mô tả / ảnh UI: …
- Kỳ vọng operator vs thực tế: …
- Bằng chứng kỹ thuật (log, API, code): …

## Chẩn đoán
- Vấn đề chính: … (một gốc)
- Triệu chứng phụ (nếu có): …
- Chokepoint: …
- Code chính + liên quan: …

## Phương án
- Làm gì (tối thiểu): …
- UI ↔ backend: … (cùng field/authority nào)
- Nhánh xử lý:
  | Trạng thái | Xử lý |
  |------------|--------|
  | … | … |
- Bảo mật (nếu chạm auth/data): …
- Phòng regression: …

## Test (nếu đổi hành vi)
- Test: …
- Trước fix: FAIL vì …
- Sau fix: PASS khi …

## PASS
- [ ] …
- [ ] …
```

**Implement:** user OK / “làm đi” / “fix” → code theo phương án → test/build → đạt PASS.

**Chỉ hỏi đáp:** vẫn đọc code; template rút gọn (bỏ Test nếu không sửa code).

---

## Rule files (Cursor)

| File | Vai trò |
|------|---------|
| `RULE.md` (file này) | Nguồn chính — workflow, tiêu chí, template đề xuất |
| `.cursor/rules/diagnose-before-fix.mdc` | Pointer + thứ tự tóm tắt — always apply |
| `.cursor/rules/root-cause-proposal.mdc` | Root cause + chokepoint |
| `.cursor/rules/test-before-code-change.mdc` | Test trước khi sửa hành vi |
