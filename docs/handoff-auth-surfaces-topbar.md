# Handoff: Auth surfaces + Topbar redesign

> Dùng file này để tiếp tục trong cuộc trò chuyện mới. Cập nhật: 2026-07-17.
> Transcript gốc: agent `c2a336dd-1dff-4817-b484-3d67729bab2c`.

## Sản phẩm nhanh

`reup-douyin`: local-first Douyin reup app (SaaS-ready). Phase hiện tại có **hai surface UI tách login**:

| Surface | URL home | Login | Ai vào được |
|---------|----------|-------|-------------|
| **Operator Studio** | `http://localhost:3000/` | `/auth/login` (`client=operator`) | mọi operator đã auth |
| **Ops Console** | `http://localhost:3000/ops` | `/auth/ops/login` (`client=ops`) | **chỉ owner/admin** |
| Swagger token helper (tertiary) | `:8000/auth/ui` | FastAPI UI | tooling đọc token — **không phải Ops Console** |

**Đừng nhầm:** Frontend ≠ “Swagger”; Backend UI ≠ Ops. Ops = app web `/ops/*` trên `:3000`.

---

## Auth đã làm (Phase A–C + tách surface)

### Backend
- Operators durable + PBKDF2; `/auth/login|register|me`, refresh/logout, rate limit, `AUTH_REGISTRATION_ENABLED`.
- JWT `iss`/`aud`; audiences: **web / ops / api**.
- `/ops/*` APIs yêu cầu ops token; Studio token → **403** trên Ops APIs.
- Migrations: `0029_auth_sessions`, `0030_auth_client` (`client` trên refresh tokens).
- Role model: bảng `operators` + `workspace_memberships.role` ∈ `owner|admin|operator|viewer` (không có bảng admin/user riêng).

### Web
- Access + refresh trong `localStorage`, soft session cookie, refresh-on-401.
- Middleware + `AuthProvider` gate theo surface (`authSurface.ts`).
- Capture Inbox dưới `/ops/extensions/.../capture-inbox` vẫn **operator** surface.
- Key files: `auth_audience_policy.py`, `operator_auth_service.py`, `apps/web/src/lib/authSurface.ts`, `middleware.ts`, `auth.tsx`, `api.ts`, trang `/auth/ops/login`.

### Bug đã sửa
- Ops login từng import sai path (`../../../lib/*` quá nông) → sửa thành `../../../../lib/*`.

### Local admin seed
```bash
cd apps/api
python -m scripts.ensure_local_admin
```
- Email: `admin@local.test`
- Password: `LocalAdmin!23456`
- Role: `owner`, workspace `local`

### Khi test auth
- Restart web/API sau đổi auth.
- Xóa localStorage session cũ khi đổi surface.
- **Không** coi `:8000/auth/ui` là Ops Console.

---

## Font Google Sans (đã tối ưu)

- Root cause: TTF ~1.9MB × 3, `url()` trước `local()`, thiếu preload.
- Fix: WOFF2 (~450–500KB), `local()` trước, preload Regular/Medium trong `layout.tsx`.
- Script: `apps/web/scripts/convert_google_sans_woff2.py`
- Assets: `apps/web/public/fonts/google-sans/*.woff2` (TTF fallback còn lại).

---

## Topbar command buttons (vừa implement xong)

### Plan
- File plan (không sửa): `~/.cursor/plans/topbar_button_redesign_e00726e7.plan.md`
- Mục tiêu: cụm Refresh / Surface switch / Navigate / Account thống nhất visual + khớp auth.

### Đã ship
**CSS** — `apps/web/src/app/globals.css` (block `.app-topbar-*`):
- Nút ~36px, radius 8px, gap 8px
- Surface switch dùng **accent xanh lá** `--accent` (bỏ xanh dương cũ)
- Focus ring accent; menu `[open]` state; bỏ `.app-topbar-command-divider`

**TSX** — `apps/web/src/components/app-shell/Topbar.tsx`:
- Icon SVG (không emoji `⇄`) + caret
- `canOpenOps` = roles có `owner|admin`
- Operator: hiện switch chỉ nếu `canOpenOps` → `loginPathForSurface("ops")` (= `/auth/ops/login`)
- Ops: luôn hiện switch → `loginPathForSurface("operator")` (= `/auth/login`) — **fail-closed** (không deep-link `/ops` hoặc `/` trực tiếp)
- Account menu hiện email/`displayName` nếu có `me`

**Test** — `apps/web/src/test/topbar.test.ts` (source contract):
```bash
cd apps/web
npx tsx src/test/topbar.test.ts
```
- Assert: `loginPathForSurface`, role gate, không `href="/ops"`, accent CSS, không divider.
- Lưu ý: test này **chưa** nằm trong script `npm test` của `package.json` (chạy tay như trên).

### PASS checklist (plan)
- [x] Studio + Ops cùng hệ visual / accent xanh lá (code)
- [x] Switch Ops chỉ owner/admin; href login surface đúng (code + test)
- [x] Refresh / Navigate / Account giữ API cũ (không đổi `topbarQuickActions`)
- [ ] Hard-refresh visual smoke trên browser — nên xác nhận thủ công nếu chưa

### Non-goals (vẫn đúng)
- Không redesign sidebar / toàn bộ page actions ngoài class chung `.app-topbar-btn`
- Không đổi nội dung `topbarQuickActions`

---

## Quy tắc repo quan trọng khi tiếp tục

- `AGENTS.md`: biên giới `apps/web` | `apps/api` | `apps/worker` | packages.
- `.cursor/rules`: diagnose → root-cause proposal → test-first (FAIL→fix→PASS) trước đổi behavior.
- Chỉ commit khi user yêu cầu rõ.
- Không live Douyin/network trong default tests.

---

## Gợi ý việc tiếp theo (nếu user chưa chỉ định)

1. Smoke UI: hard-refresh Studio + Ops với `admin@local.test` — kiểm tra cụm nút, switch, menu.
2. Smoke role: login operator thường (không owner/admin) → **không** thấy “Open Ops Console”.
3. (Optional) Thêm `tsx src/test/topbar.test.ts` vào `apps/web/package.json` → `"test"`.
4. Không đụng lại plan file; nếu redesign tiếp thì plan mới.

---

## File chạm gần đây nhất

- `apps/web/src/components/app-shell/Topbar.tsx`
- `apps/web/src/app/globals.css` (topbar block ~L352+)
- `apps/web/src/test/topbar.test.ts`
- Auth liên quan (đã ổn định trước topbar): `apps/web/src/lib/authSurface.ts`, `auth.tsx`, `middleware.ts`
