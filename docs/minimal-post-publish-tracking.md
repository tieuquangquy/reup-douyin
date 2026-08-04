# Minimal Post-Publish Tracking

Phase 1 tracks only the fields needed to know whether a post went live and where to find it.

## Tracked On PublishAttempt

- platform
- platform account
- attempt number
- internal status
- external publish/media/reel ids
- external permalink
- external publication status
- reconciliation status
- last status checked time
- safe request/response summaries
- warnings and errors

## Tracked On PublishDraft

- latest publish attempt id
- canonical publish attempt id
- current external publish id
- current external permalink
- current publication status
- published time when known
- last publish sync time
- publication summary JSON

## Added After The Minimal Phase 1 Contract

`Publication Metrics V1` now stores cumulative snapshots for views, likes, comments,
shares, saves and selected platform-specific reach/watch fields. It also derives deltas,
view velocity and engagement rates. See `docs/publication-metrics-v1.md`.

Still not tracked here:

- affiliate clicks, orders, commission or revenue attribution
- comment moderation
- inbox state
- audience/follower history outside publication-attributed follower gain

## Use In UI

The publish draft page can display:

- publication status summary;
- canonical external link;
- warning if operator attention is needed;
- recent attempts with refresh action.
