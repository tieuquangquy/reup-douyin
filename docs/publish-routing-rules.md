# Publish Routing Rules

Routing rules are deterministic hints for choosing a `PlatformAccount`. They do not publish content and they do not block operator override.

## Evaluation Order

1. Load ready/scheduled `PublishDraft`.
2. Load accounts for the draft platform.
3. Compute account health.
4. Apply active routing rules sorted by `priority desc`, then creation order.
5. Evaluate eligibility.
6. Rank eligible accounts by score.
7. Return recommended and blocked accounts with reasons.

## Supported Match Fields

Phase 1 supports simple JSON match keys:

- `niche`
- `niche_tag`
- `niche_label`
- `preset`
- `preset_name`
- `source_video_id`

Example:

```json
{
  "match_json": { "niche": "home_kitchen" },
  "action_json": {
    "recommend_account_ids": ["00000000-0000-0000-0000-000000000001"],
    "exclude_account_ids": [],
    "require_manual_review": false
  }
}
```

## Actions

- `recommend_account_ids`: add a routing score boost.
- `exclude_account_ids`: mark accounts as blocked for this recommendation.
- `require_manual_review`: add a warning shown in the control plane.

## Override Policy

Operator override remains available. If an ineligible account is used with override, the draft assignment status becomes `OVERRIDDEN` and the blocking reasons are persisted in `assignment_metadata_json`.

