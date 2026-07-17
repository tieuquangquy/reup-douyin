# Project Context

## Product Summary

`reup-douyin` is a local-first, SaaS-ready web application for an MMO/video operator who wants to find high-performing Douyin videos, review them, and prepare localized reuploads for other platforms.

## Target Users

- Phase 1: one Windows operator running the stack locally.
- Future: multi-user SaaS with workers, queues, cloud storage, auth, and deployment hardening.

## Core Workflow

1. Connect or open a Douyin profile.
2. Scan/import profile videos.
3. Store discovered videos and metadata.
4. Review, filter, score, and select promising candidates.
5. Process selected videos for reupload: rewrite caption/script, create voice, generate subtitles, cover/remove Chinese text, render/export final video.
6. Prepare and publish/export to target platforms.

## Known Unfinished Area

The most fragile unfinished area is Douyin profile scanning/import. There are two parallel-ish intake surfaces:

- API/source ingest path: `/source-profiles/ingest`, `SourceIngestService`, `DouyinProfileAdapter`.
- Chrome extension whole-profile harvest path: popup `Scan Profile` -> content script/profile scanner -> backend capture session/inbox endpoints.

The active Scan Profile UX appears to be in the browser extension, not the Next.js intake page.

## Assumptions

- The project is meant to run with `npm run dev` on Windows.
- Local dev uses FastAPI on port 8000, Next.js on port 3000, and a Python worker.
- PostgreSQL/Redis are target production services, but local data includes SQLite-like files under `apps/api/data`.
- Real Douyin crawling may require Playwright, a logged-in browser profile/session, and careful handling of anti-bot/challenge pages.

## Key Business Priorities

- Prioritize the first working product loop: scan/import videos -> display candidates -> select videos -> process/export.
- Make Scan Profile reliable and observable before deep processing features.
- Avoid risky live scraping during debugging; prefer extension/browser-session capture and deterministic test fixtures.
