# Operator Feedback Loop

Operator feedback is a lightweight annotation that connects published output quality back to pipeline decisions.

## Feedback Fields

- `quality_label`: `GOOD`, `ACCEPTABLE`, or `WEAK`
- `publish_confidence`: `SCALABLE`, `NEEDS_IMPROVEMENT`, or `DO_NOT_REUSE_PATTERN`
- `root_cause`: optional operational hint
- `note`: free-form short note

Root cause examples:

- source selection issue
- transcript quality issue
- TTS issue
- subtitle issue
- render issue
- publish issue
- risk false positive
- CTA/caption issue

## Targets

Feedback can attach to:

- source video
- render output
- publish draft
- publish attempt

The dashboard uses publish draft feedback first because it maps cleanly to a complete output/publication.

## How Feedback Helps

Feedback is aggregated by:

- source profile
- niche label if available
- filter/scoring preset

This gives the operator early signals about which inputs and presets are worth repeating. It is not ML ranking and does not automatically change scoring.

