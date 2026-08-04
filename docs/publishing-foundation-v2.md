# Publishing Foundation V2

Publishing Foundation V2 separates an external post from the request and attempts that
produced it.

## Authorities

- `PublishDraft`: reviewed platform metadata and intended account/schedule.
- `PublishAttempt`: one durable execution attempt, including failures and reconciliation.
- `PlatformPublication`: one externally confirmed post identified by platform, account and
  external publish id.

A draft can have multiple attempts and, after an accidental duplicate publish, multiple
real publications. All confirmed external posts are retained. Exactly one publication is
marked `is_canonical` according to the draft's canonical attempt.

## Durable publish flow

`POST /publish-drafts/{id}/publish` no longer uploads media in the HTTP request. It:

1. reruns the publish gate;
2. creates a `PublishAttempt` in `QUEUED`;
3. creates one `PUBLISH_CONTENT` job bound to that attempt;
4. returns the queued attempt immediately.

The worker executes that exact attempt. Publish jobs use one automatic attempt because a
transport failure can occur after the platform accepted the video. A resumed attempt that
already crossed the external boundary is failed closed or routed to reconciliation; it is
never uploaded again automatically.

## Publication materialization

After success or reconciliation, `PlatformPublicationService` upserts by:

```text
workspace + platform + platform_account + external_publish_id
```

Only externally confirmed `PUBLISHED` attempts create a new publication. Existing
publication rows can later move to `REMOVED`, `FAILED` or `NOT_FOUND` when platform status
sync provides that evidence.

## Read API

- `GET /platform-publications`
- `GET /platform-publications/{publication_id}`
- `GET /publish-drafts/{publish_draft_id}/platform-publications`

## Local operational validation

Apply Alembic revision `0033_publication_authority` before enabling this flow. Revision
identifiers are kept within Alembic's default 32-character `version_num` limit.

The PostgreSQL pilot uses a local mock connector and an approved local render. It must
prove all of these invariants without making an external network request:

1. enqueue creates one attempt and one `PUBLISH_CONTENT` job;
2. worker execution creates one confirmed, canonical publication;
3. resuming the terminal attempt makes zero additional publish calls;
4. repeated authority sync and reconciliation keep exactly one publication;
5. persisted request summaries do not contain the private local video path.

Direct execution of a queued job commits `RUNNING` before the runner's cancellation
refresh, matching the durable state established by the normal worker claim path.

## Explicit non-goals

- provider metric collection (metric snapshots are implemented separately in
  `docs/publication-metrics-v1.md`);
- topic classification;
- affiliate product matching;
- native product tags;
- affiliate comments;
- new platform connectors;
- a scheduled-publish dispatcher.

Those features should attach to `PlatformPublication` in later steps rather than to a
draft or transient attempt.
