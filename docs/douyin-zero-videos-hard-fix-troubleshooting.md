# Douyin Zero Videos Hard Fix Troubleshooting

## What Changed

The canonical Douyin intake flow no longer treats shell/challenge responses as successful zero-video fetches.

Before this fix, `/intake` could finish as:

- zero videos discovered
- zero candidates matched
- no explicit fetch error

Now the same class of failure is surfaced as a fetch-stage issue with explicit diagnostics.

## Current Classification Categories

- `success`
- `blocked_response`
- `login_required`
- `parse_failed`
- `parse_zero_videos`
- `true_zero_videos`
- `filter_zero_candidates`

## How To Read The New Outcomes

### `blocked_response`

Meaning:

- the connected account/session hit a challenge or blocked page before videos loaded

What to do:

- validate the account again
- try a healthier account
- if a persistent browser profile exists, retry from that profile

### `login_required`

Meaning:

- the connected account/session was redirected back to login

What to do:

- reconnect or revalidate the account in `/accounts/douyin`

### `parse_failed`

Meaning:

- Douyin rendered something usable enough to suggest content exists, but the current canonical parser could not extract the video payload

What to do:

- capture the run id
- compare with browser-backed fetch behavior
- update parser strategy without adding a second persistence pipeline

### `parse_zero_videos`

Meaning:

- HTTP fetch returned an HTML shell with no embedded profile/video payloads
- this is not treated as a real zero-video profile anymore

What to do:

- inspect the selected account and network path first
- inspect `fetch_observability.stages.response_classification`
- inspect `raw_summary_json.response_shape` and `embedded_document_count`

### `true_zero_videos`

Meaning:

- the response was parseable and explicitly yielded zero videos

What to do:

- verify the profile actually has no public videos

### `filter_zero_candidates`

Meaning:

- videos were fetched successfully
- the candidate filter stage matched zero items

What to do:

- adjust intake thresholds, date range, or preset

## Operator-Facing Signals

The intake result and run history now expose enough safe detail to distinguish:

- fetch-stage failure
- true zero videos
- filter zero candidates

Important fields:

- `diagnostics_id`
- `fetch_stage`
- `fetch_stage_code`
- `fetch_stage_message`
- `parser_strategy`
- `videos_discovered_count`
- `videos_normalized_count`
- `videos_persisted_count`
- `fetch_observability`

## Reproduced Real Case For This Fix

For the reproduced profile/account:

- HTTP fetch returned an HTML shell
- `embedded_document_count = 0`
- a Playwright probe with the same connected session reached a challenge page

So the previous `zero videos` result was not a true profile state. It was a fetch-stage misclassification.

## Remaining External Limitations

- Douyin can still challenge a valid connected account.
- A browser-backed account can still pass high-level validation but fail profile-feed fetch because the profile route is challenged.
- This fix makes the failure explicit and operationally debuggable. It does not guarantee Douyin will always allow profile feed access.
