# Facebook Reels Connector

Facebook Reels for Pages is the first real publish connector for `reup-douyin`.

## Why Facebook First

- Phase 1 needs one real connector before adding more platforms.
- Facebook Page publishing fits the existing `PublishDraft -> RenderOutput -> RiskGate` flow.
- The Meta Reels publishing flow is explicit: create upload session, upload video, finish/publish.
- The connector shape is reusable for future TikTok/YouTube connectors.

## Architecture

```text
PublishDraft READY
  -> PublishGateService
  -> PlatformAccountService
  -> PublishAttemptService
  -> PublishConnector interface
  -> FacebookReelsConnector
  -> PublishAttempt result
  -> optional status refresh/reconciliation
```

Core publish orchestration owns lifecycle, idempotency, and persistence. The Facebook connector owns only platform transport mapping.

## Facebook Flow

The phase 1 connector follows Meta's Reels Publishing collection:

1. Create Reel upload session with `POST /{page-id}/video_reels` and `upload_phase=start`.
2. Upload local video bytes to `rupload.facebook.com` using `Authorization: OAuth <page-token>`, `offset: 0`, and `file_size`.
3. Finish publish with `upload_phase=finish`, `video_state=PUBLISHED`, `title`, and `description`.
4. Refresh status when a result is ambiguous or needs reconciliation with `GET /{external-reference}`.

The connector stores only safe response summaries. It must never persist or log the full page access token.

Before a publish is admitted, the API applies Page-level safety guardrails:

- OAuth must verify `pages_manage_posts` and the Page `CREATE_CONTENT` task;
- only one active attempt may exist for a Page;
- unresolved external outcomes block another attempt;
- conservative warm-up, interval, daily-attempt and failure budgets are
  enforced per Page;
- rate-limit errors create a cooldown, while token/permission/restriction
  errors put the Page on hold until it is reconnected;
- Graph credentials are sent in the HTTPS `Authorization` header, not URL
  query parameters.

These controls reduce avoidable API pressure and duplicate publishes. They do
not guarantee immunity from Meta enforcement; operators remain responsible for
rights, policy, Page quality and approved content.

Sources used while implementing this connector:

- Meta Postman collection, Reels Publishing overview
- Meta Postman collection, Create Reel
- Meta Postman collection, Upload Local Reel
- Meta Postman collection, Publish Reel

## Inputs

- `PublishDraft` with status `READY`
- approved `RenderOutput`
- final render `MediaAsset`
- active `PlatformAccount` with platform `FACEBOOK_REELS`
- risk gate allowing publish

## Outputs

- `PublishAttempt`
- external Facebook video/reel id when successful
- external publication status and permalink when available
- request/response summary
- error code/message when failed
- reconciliation status when the result is ambiguous

## Known Phase 1 Limits

- Manual token/account setup only.
- No OAuth onboarding UI.
- No post analytics.
- No comment inbox.
- No scheduled auto-publish runner.
- No webhook status sync yet; phase 1 uses explicit status refresh from API/UI.
