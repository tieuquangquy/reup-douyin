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

## Not Tracked In Phase 1

- views
- likes
- comments
- shares
- follower growth
- comment moderation
- inbox state

Those belong to a later analytics/engagement phase.

## Use In UI

The publish draft page can display:

- publication status summary;
- canonical external link;
- warning if operator attention is needed;
- recent attempts with refresh action.

