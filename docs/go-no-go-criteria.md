# Go / No-Go Criteria For Publish Connector

Use this after the pre-beta pilot and bug bash. The decision is whether the repo is ready to build a real publish connector for one target platform.

## Quality Criteria

Go if:

- At least 70% of approved final renders in the pilot are usable after normal transcript edits.
- Subtitle timing and narration quality issues are visible before mark publish-ready.
- Operator does not need to manually reconstruct lost metadata or manifests.

No-go if:

- Final render output frequently points to stale narration/subtitle/source assets.
- More than 30% of final renders require rework due to pipeline state confusion rather than content quality.
- Transcript editor cannot preserve edits reliably.

## Stability Criteria

Go if:

- No unresolved `P0_BLOCKER`.
- No unresolved P1 affecting final review, publish draft, risk gating, or render output selection.
- Failed jobs include specific error codes and appear in `/ops/metrics`.
- Retry/resume decisions are clear from UI/API/runbooks.

No-go if:

- Jobs get stuck without visible status.
- Retry creates duplicate current assets or ambiguous current renders.
- Publish draft ready can bypass critical open risk without explicit operator decision.

## Throughput Criteria

Go if:

- Light pilot completes in one operator session.
- Medium pilot identifies bottlenecks but does not require code-level intervention.
- `/ops/metrics` captures backlog, failure categories, and retry counts during pilot.

No-go if:

- Operator spends more time debugging IDs/state than reviewing content.
- Local worker backlog hides failed jobs.
- Common stages rerun unnecessarily after unchanged inputs.

## Operator UX Criteria

Go if:

- Operator can complete review board, transcript edit, final review, and publish draft without developer help.
- Dirty state and before/after compare prevent accidental edit loss.
- Risk warnings are understandable and not dismissed as noise.

No-go if:

- Bulk actions regularly surprise the operator.
- Approve export, publish-ready, and publish draft ready remain confusing.
- Mark-ready flow does not explain why it is blocked.

## Risk / Compliance Clarity Criteria

Go if:

- Risk scan is clearly presented as heuristic/operator-assist.
- High/critical warnings are prominent.
- `accept_with_warning` records an explicit decision and note.

No-go if:

- UI implies legal certainty.
- Waived/resolved/open statuses are unclear.
- Old risk decisions silently apply to materially changed renders.

## Packaging / Docs Readiness Criteria

Go if:

- A new dev/operator can follow `docs/local-operator-guide.md`.
- Pilot templates are filled consistently.
- Runbooks cover observed failures or are updated during pilot.

No-go if:

- Setup requires undocumented steps.
- Failure recovery depends on code inspection.
- Demo/pilot cannot be repeated after reset/reseed.

## Recommended Decision Format

```text
Decision: GO / CONDITIONAL GO / NO-GO
Target connector: <platform>
Evidence window: <dates>
Pilot load: light / medium / heavy
Open P0: <count>
Open P1: <count>
Top blockers:
Top accepted risks:
Required fixes before connector:
```

