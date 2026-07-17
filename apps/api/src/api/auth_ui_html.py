"""Static HTML for the FastAPI backend auth UI (`GET /auth/ui`).

Kept separate from the Next.js Operator login at :3000/auth/login.
Same identity (`POST /auth/login`); this page only helps API/Swagger operators
obtain a read-only bearer token (client=api-ui).
"""

from __future__ import annotations

AUTH_UI_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>reup-douyin · API Console</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg-0: #07111a;
      --bg-1: #0c1a24;
      --panel: rgba(12, 28, 38, 0.92);
      --text: #e8f1f4;
      --muted: #8aa0ab;
      --line: #1e3542;
      --accent: #2ec4b6;
      --accent-dim: #1a8f85;
      --warn: #e9b949;
      --danger: #ef6b6b;
      --ok: #5ddea0;
      --glow: rgba(46, 196, 182, 0.18);
      --sans: "IBM Plex Sans", "Segoe UI", sans-serif;
      --mono: "IBM Plex Mono", ui-monospace, monospace;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(900px 520px at 12% 8%, rgba(46, 196, 182, 0.14), transparent 55%),
        radial-gradient(700px 480px at 88% 92%, rgba(40, 90, 120, 0.28), transparent 50%),
        linear-gradient(160deg, var(--bg-0), var(--bg-1) 55%, #0a1620);
      min-height: 100vh;
    }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(240px, 0.95fr) minmax(320px, 1.05fr);
    }
    @media (max-width: 860px) {
      .shell { grid-template-columns: 1fr; }
      .brand { min-height: 220px; padding: 2rem 1.4rem 1.2rem; }
    }
    .brand {
      position: relative;
      padding: 3.2rem 2.6rem;
      border-right: 1px solid var(--line);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow: hidden;
    }
    .brand::before {
      content: "";
      position: absolute;
      inset: auto -20% -30% 20%;
      height: 60%;
      background:
        repeating-linear-gradient(
          -18deg,
          transparent,
          transparent 10px,
          rgba(46, 196, 182, 0.05) 10px,
          rgba(46, 196, 182, 0.05) 11px
        );
      pointer-events: none;
    }
    .brand-top { position: relative; z-index: 1; }
    .mark {
      display: inline-flex;
      align-items: center;
      gap: 0.55rem;
      margin-bottom: 1.6rem;
      font-family: var(--mono);
      font-size: 0.78rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
    }
    .mark-dot {
      width: 0.55rem;
      height: 0.55rem;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 4px var(--glow);
      animation: pulse 2.4s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.15); opacity: 0.75; }
    }
    .brand h1 {
      margin: 0 0 0.75rem;
      font-size: clamp(1.8rem, 3vw, 2.45rem);
      line-height: 1.1;
      font-weight: 700;
      letter-spacing: -0.02em;
      max-width: 12ch;
    }
    .brand p {
      margin: 0;
      max-width: 34ch;
      color: var(--muted);
      font-size: 0.98rem;
      line-height: 1.55;
    }
    .brand-meta {
      position: relative;
      z-index: 1;
      display: grid;
      gap: 0.55rem;
      margin-top: 2rem;
      font-family: var(--mono);
      font-size: 0.75rem;
      color: var(--muted);
    }
    .brand-meta span { color: var(--text); }
    .panel-wrap {
      display: grid;
      place-items: center;
      padding: 2rem 1.25rem;
    }
    .panel {
      width: min(440px, 100%);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 1.55rem 1.45rem 1.4rem;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(8px);
      animation: rise 420ms ease-out;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: none; }
    }
    .badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
      margin-bottom: 0.9rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.22rem 0.55rem;
      border: 1px solid var(--line);
      border-radius: 999px;
      font-family: var(--mono);
      font-size: 0.68rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .badge.warn {
      border-color: rgba(233, 185, 73, 0.45);
      color: var(--warn);
      background: rgba(233, 185, 73, 0.08);
    }
    .panel h2 {
      margin: 0 0 0.4rem;
      font-size: 1.35rem;
      font-weight: 650;
    }
    .copy {
      margin: 0 0 1.2rem;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }
    label {
      display: grid;
      gap: 0.35rem;
      margin-bottom: 0.85rem;
      font-size: 0.82rem;
      color: var(--muted);
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 3px;
      background: #07131a;
      color: var(--text);
      padding: 0.7rem 0.8rem;
      font: inherit;
      transition: border-color 160ms ease, box-shadow 160ms ease;
    }
    input:focus {
      outline: none;
      border-color: var(--accent-dim);
      box-shadow: 0 0 0 3px var(--glow);
    }
    button.primary {
      width: 100%;
      margin-top: 0.35rem;
      border: 0;
      border-radius: 3px;
      background: linear-gradient(180deg, #35d4c5, var(--accent-dim));
      color: #041218;
      font: inherit;
      font-weight: 650;
      padding: 0.78rem 0.9rem;
      cursor: pointer;
      transition: transform 120ms ease, filter 120ms ease;
    }
    button.primary:hover { filter: brightness(1.05); }
    button.primary:active { transform: translateY(1px); }
    button.primary:disabled { opacity: 0.65; cursor: wait; }
    button.ghost {
      border: 1px solid var(--line);
      background: #0a1820;
      color: var(--text);
      border-radius: 3px;
      font-family: var(--mono);
      font-size: 0.72rem;
      padding: 0.3rem 0.55rem;
      cursor: pointer;
    }
    .error {
      margin: 0.75rem 0 0;
      color: var(--danger);
      font-size: 0.88rem;
    }
    .result {
      display: none;
      margin-top: 1.15rem;
      padding-top: 1rem;
      border-top: 1px solid var(--line);
    }
    .result.visible { display: block; animation: rise 320ms ease-out; }
    .result h3 {
      margin: 0 0 0.65rem;
      font-size: 0.92rem;
      color: var(--ok);
      font-weight: 600;
    }
    .token-block { margin-bottom: 0.85rem; }
    .token-block header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      margin-bottom: 0.35rem;
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    textarea {
      width: 100%;
      min-height: 4.4rem;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 3px;
      background: #050e14;
      color: var(--text);
      font-family: var(--mono);
      font-size: 0.7rem;
      line-height: 1.45;
      padding: 0.55rem 0.65rem;
    }
    .hint {
      margin: 0.55rem 0 0;
      color: var(--muted);
      font-size: 0.8rem;
      line-height: 1.45;
    }
    .links {
      margin: 1.1rem 0 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem 1rem;
      font-size: 0.86rem;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .studio {
      margin-top: 1rem;
      padding-top: 0.9rem;
      border-top: 1px dashed var(--line);
      font-size: 0.82rem;
      color: var(--muted);
      line-height: 1.45;
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="brand" aria-label="API Console brand">
      <div class="brand-top">
        <div class="mark"><span class="mark-dot" aria-hidden="true"></span> Backend surface</div>
        <h1>API Console</h1>
        <p>
          Trang phụ trợ lấy bearer cho Swagger (<code>/docs</code>).
          Đây <strong>không</strong> phải Ops Console —
          Ops Console nằm ở <code>:3000/auth/ops/login</code> (owner/admin).
          Operator Studio: <code>:3000/auth/login</code>.
        </p>
      </div>
      <div class="brand-meta">
        <div>service <span>reup-douyin API</span></div>
        <div>client <span>api-ui</span></div>
        <div>docs <span>/docs · /auth/ui</span></div>
      </div>
    </aside>
    <div class="panel-wrap">
      <main class="panel">
        <div class="badge-row">
          <span class="badge">FastAPI · :8000</span>
          <span class="badge warn">Read-only product writes</span>
        </div>
        <h2>Sign in</h2>
        <p class="copy">
          Dùng tài khoản operator (owner/admin khuyến nghị). Form gọi
          <code>POST /auth/login</code> với <code>client=api-ui</code>.
        </p>
        <form id="login-form" autocomplete="on">
          <label>
            Email
            <input id="email" name="email" type="email" required autocomplete="username" placeholder="admin@local.test" />
          </label>
          <label>
            Password
            <input id="password" name="password" type="password" required minlength="8" autocomplete="current-password" />
          </label>
          <label>
            Workspace slug
            <input id="workspace" name="workspace_slug" required minlength="3" value="local" />
          </label>
          <button class="primary" id="submit" type="submit">Get API token</button>
          <p id="error" class="error" hidden></p>
        </form>
        <section id="result" class="result" aria-live="polite">
          <h3>Tokens issued</h3>
          <div class="token-block">
            <header>
              <span>Access token</span>
              <button type="button" class="ghost" data-copy="access">Copy</button>
            </header>
            <textarea id="access-token" readonly></textarea>
          </div>
          <div class="token-block">
            <header>
              <span>Refresh token</span>
              <button type="button" class="ghost" data-copy="refresh">Copy</button>
            </header>
            <textarea id="refresh-token" readonly></textarea>
          </div>
          <p class="hint">
            Swagger → <strong>Authorize</strong> →
            <code>Bearer &lt;access_token&gt;</code>.
            Muốn POST/PUT/PATCH/DELETE: lấy token web từ
            <code>:3000/auth/login</code>.
          </p>
        </section>
        <p class="links">
          <a href="/docs">Open Swagger</a>
          <a href="/redoc">ReDoc</a>
          <a href="/openapi.json">OpenAPI</a>
        </p>
        <p class="studio">
          Operator Studio (frontend, full write):
          <a href="http://localhost:3000/auth/login">localhost:3000/auth/login</a>
        </p>
      </main>
    </div>
  </div>
  <script>
    (function () {
      var form = document.getElementById("login-form");
      var errorEl = document.getElementById("error");
      var resultEl = document.getElementById("result");
      var submitBtn = document.getElementById("submit");
      var accessEl = document.getElementById("access-token");
      var refreshEl = document.getElementById("refresh-token");

      function showError(message) {
        errorEl.hidden = false;
        errorEl.textContent = message || "Login failed";
      }

      form.addEventListener("submit", async function (event) {
        event.preventDefault();
        errorEl.hidden = true;
        resultEl.classList.remove("visible");
        submitBtn.disabled = true;
        submitBtn.textContent = "Signing in…";
        try {
          var response = await fetch("/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: document.getElementById("email").value,
              password: document.getElementById("password").value,
              workspace_slug: document.getElementById("workspace").value,
              client: "api-ui"
            })
          });
          var payload = {};
          try { payload = await response.json(); } catch (_) {}
          if (!response.ok) {
            var detail = payload.detail;
            if (Array.isArray(detail)) {
              detail = detail.map(function (item) { return item.msg || JSON.stringify(item); }).join("; ");
            }
            throw new Error(detail || ("HTTP " + response.status));
          }
          accessEl.value = payload.access_token || "";
          refreshEl.value = payload.refresh_token || "";
          resultEl.classList.add("visible");
        } catch (err) {
          showError(err && err.message ? err.message : "Login failed");
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = "Get API token";
        }
      });

      document.querySelectorAll("[data-copy]").forEach(function (button) {
        button.addEventListener("click", async function () {
          var kind = button.getAttribute("data-copy");
          var value = kind === "refresh" ? refreshEl.value : accessEl.value;
          if (!value) return;
          try {
            await navigator.clipboard.writeText(value);
            button.textContent = "Copied";
            setTimeout(function () { button.textContent = "Copy"; }, 1200);
          } catch (_) {
            (kind === "refresh" ? refreshEl : accessEl).select();
          }
        });
      });
    })();
  </script>
</body>
</html>
"""
