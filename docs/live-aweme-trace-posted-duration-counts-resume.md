# Resume — Live aweme Trace Posted/Duration/Counts

## Current status

Docs-first initialization completed.

Trace scope in this run is explicitly narrowed to one real item:

- `7489123456789012345`

The other two IDs were provided but lacked concrete (non-placeholder) field values at evidence time:

- `7489123456789012346`
- `7489123456789012347`

Primary log file: `docs/live-aweme-trace-posted-duration-counts-log.md`

## Scope lock

Live diagnosis only:

- Trace A→F for posted/duration/view-like-comment-share fields.
- Determine exact first-loss stage per field.
- No broad fix/refactor/redesign in this pass.

## Remaining execution order

1. Optional: add concrete evidence for `7489123456789012346` and `7489123456789012347`
2. Finalize summary

## Notes

Terminal output streaming is intermittent in this environment. Prefer artifacted/logged evidence snippets per stage and attach exact aweme-specific values for each field.
