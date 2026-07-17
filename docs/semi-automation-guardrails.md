# Semi-Automation Guardrails

Step 22 adds semi-automation policy checks. It does not add full autopilot.

## Auto-Assign Allowed Only When

- draft status is `READY`
- top routing hint has `high` confidence
- top account health is `HEALTHY`
- no open high/critical/blocking risk flags exist
- draft is not already marked as a manual override pattern

If any condition fails, the system returns `requires_manual_review`.

## Auto-Schedule Fill Allowed Only When

- draft is `READY` or `SCHEDULED`
- draft has an assigned account
- schedule confidence is `high`
- scheduling hint has no warnings

## Always Manual

- publish action remains manual
- risk override remains manual
- low confidence routing remains manual
- ambiguous publish outcomes remain manual/reconcile-first

The guardrails are intentionally conservative because publishing creates external side effects.

