# Operator Control Plane

The publish control plane lives at `/publish-control`.

## Purpose

The screen helps an operator route publish-ready drafts across multiple Facebook Pages before triggering publish attempts.

It shows:

- account/Page health
- assigned and unassigned ready drafts
- scheduled drafts
- drafts needing attention
- routing rule summary
- recommended account per draft

## Main Actions

- assign a draft to its recommended account
- unassign a draft
- bulk assign selected drafts to one account
- put an account on manual hold or remove hold
- refresh queue and account health

The UI is intentionally not a social management portal. It is a local operator control surface for routing and backlog balance.

Bulk assignment is all-or-nothing at the service layer. The backend validates every selected draft against the target account before applying any assignment, so one invalid item does not leave the batch half-routed.

## Data Flow

Frontend calls:

- `GET /publish-control/queue`
- `GET /routing-rules`
- `POST /publish-drafts/{id}/assign-account`
- `POST /publish-drafts/{id}/unassign-account`
- `POST /publish-drafts/bulk-assign`

Backend services:

- `AccountHealthService`
- `RoutingRecommendationService`
- `DraftAssignmentService`
- `ControlQueueService`

## Known Limits

- Assignment does not automatically publish.
- Scheduling remains the phase 1 scheduling skeleton.
- Bulk assignment is manual and immediate.
- Account health is computed from recent local publish data, not platform-side analytics.
