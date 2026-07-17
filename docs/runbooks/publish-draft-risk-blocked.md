# Publish Draft Risk Blocked Runbook

## Symptoms

- Publish draft cannot be marked `READY`.
- UI says risk warnings require decision.
- Gate summary has `can_continue = false`.

## Common Causes

- Open `CRITICAL` or `BLOCKING` warning.
- Open `HIGH` warning without operator decision.
- Missing caption/CTA/hashtags created platform policy risk.
- Render warnings propagated into final review.

## Checks

- `GET /targets/PUBLISH_DRAFT/{publish_draft_id}/risk-summary`.
- `GET /risk-flags?target_type=PUBLISH_DRAFT&target_id={publish_draft_id}`.
- Check latest operator decision.
- Review warning title, description, evidence summary.

## Immediate Handling

- Resolve warning if it was fixed.
- Waive warning if it is not relevant.
- Use `ACCEPT_WITH_WARNING` only when operator understands and accepts the risk.
- Use `NEEDS_FIX` when the draft should return to caption/transcript/render edits.

## Rerun / Decision

- Rerun scan after editing caption/CTA/hashtags.
- Mark needs_fix for content/timing/render issues.
- Reject when risk is unacceptable for alpha.
- Do not treat risk scan as legal approval.
