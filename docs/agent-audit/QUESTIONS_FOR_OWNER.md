# Questions For Owner

## Product Decisions

1. Which import path should be canonical for the MVP: the Chrome extension `Scan Profile` flow, the API-only `/source-profiles/ingest` flow, or both?
2. What is the minimum successful result for a profile scan: a list of video URLs only, URLs plus metrics, or fully captured modal/detail metadata?
3. Should users scan only their own Douyin accounts/profiles, competitor/public profiles, or both?
4. What is the target MVP workflow after import: review/filter only, enqueue processing, or end-to-end rewritten/exported videos?
5. What quality filters matter most for MMO operators: views, likes, comments, shares, duration, posting date, text density, niche keywords, or custom scoring?
6. Should duplicate videos across repeated scans be merged silently, shown as updates, or saved as separate crawl/session history?

## Technical Choices

1. Should live Douyin fetching remain disabled by default (`DOUYIN_ENABLE_LIVE_FETCH=false`) and rely on extension/browser capture, or should the API become responsible for live profile fetches?
2. Should the current local polling worker stay for Phase 1, or should Redis-backed queue processing become mandatory before more video-processing features are built?
3. Should PostgreSQL be the only supported database, or should the existing local SQLite-style development data remain supported?
4. Should Chrome extension state be treated as temporary scan state only, with backend capture inbox as source of truth?
5. Should the older source-ingest/crawl-session model be unified with capture-inbox sessions, or should they remain separate concepts?
6. Which browser automation path should be preferred long term: user-operated Chrome extension, API Playwright browser connect, or both with clear responsibilities?

## Credentials, API, And Cookies

1. Who owns the Douyin login/session used for scanning: each operator user, a shared local browser profile, or an API-managed account pool?
2. Is it acceptable to store encrypted Douyin cookies/session material locally or in the backend database?
3. What authentication mode should be used during local development: API auth required with JWT, or an easier local bypass?
4. What production value should replace the default local JWT secret and where should it be managed?
5. Are proxies required for Douyin access, and if so should proxy config be per workspace, per account, or global?
6. Should the extension require an explicit backend token sync from the web app before Scan Profile can run?

## Deployment And Operations

1. Is the intended deployment single-machine local Windows first, Docker Compose on a server, or a hosted multi-tenant SaaS?
2. Should the product support Windows-only operator workflows, or macOS/Linux operators too?
3. What environment is the first real deployment target: local PC, VPS, cloud container service, or private LAN?
4. How should generated media and downloaded source assets be stored: local disk, mounted volume, S3-compatible object storage, or another provider?
5. What monitoring is required for alpha: logs only, admin dashboard, structured job events, alerting, or replayable scan diagnostics?
6. Should failed Scan Profile runs keep full diagnostic payloads for debugging, and if so for how long?

## UX Questions

1. Where should the primary user start a Douyin import: web intake page, extension popup, capture inbox page, or a dedicated Scan Profile wizard?
2. What should the user see when Scan Profile fails: a short friendly message, detailed diagnostics, or both with an advanced panel?
3. Should the UI guide users through Douyin login/challenge/profile navigation before enabling Scan Profile?
4. Should imported videos appear immediately in Capture Inbox, Review Board, or both?
5. Should repeated scans of the same profile show a session history/timeline to compare newly discovered videos?
6. What should the empty-state experience be when a scan succeeds technically but finds zero usable videos?

## Data Retention, Legal, And Compliance

1. What content is the product allowed to download, store, transform, and republish from Douyin?
2. Should the system store original videos, thumbnails, captions, and metric snapshots indefinitely or expire them after a retention window?
3. Does the product need workspace/user-level deletion of all imported profile data and generated media?
4. Are there restrictions on storing creator handles, profile URLs, sec_uid values, or engagement metrics?
5. What level of audit trail is required for imported content and generated/reuploaded outputs?
6. Should the app include operator acknowledgements or policy checks before processing third-party content?

## Decisions Needed Before Fixing Scan Profile

1. Confirm the exact failing user action and surface: extension popup `Scan Profile`, web intake/profile scan, or another button.
2. Provide the visible error message and whether any capture session appears afterward.
3. Confirm whether the user is logged into Douyin in the browser tab used by the extension.
4. Confirm whether the extension backend URL points to the running API and whether API auth is enabled.
5. Confirm the expected output after a successful scan: queue only, capture inbox items, review candidates, or all of these.
