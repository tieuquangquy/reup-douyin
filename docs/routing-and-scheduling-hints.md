# Routing And Scheduling Hints

Routing and scheduling hints build on the Step 21 publish control plane.

## Routing Hints

`GET /optimization/routing-hints?publish_draft_id=...` ranks accounts using:

- Step 21 routing recommendation
- account health
- routing rules
- backlog/reconciliation signals
- outcome context

For drafts that already have publish attempts, outcome context uses that draft's `OUTCOME_SCORE_V1`. For READY drafts that have not been published yet, routing uses a neutral pre-publish context score and relies more heavily on account health/rules/backlog. This avoids pretending the system knows the outcome before a real attempt exists.

Each account recommendation includes:

- confidence score
- confidence label
- health status
- reasons
- warnings

## Scheduling Hints

`GET /optimization/scheduling-hints?publish_draft_id=...` returns simple phase 1 publish slot suggestions.

Current strategy:

- space suggested slots by a few hours
- pair slots with the top account recommendations
- warn when routing confidence is not high
- require manual choice when no eligible account exists

This is not a scheduler. It is an operator-facing suggestion layer.

## Explainability

Every hint must explain why an account or slot is suggested, and why automation is blocked.
