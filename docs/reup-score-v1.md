# Reup Score V1

`REUP_SCORE_V1` is deterministic and explainable. It produces a 0-100 score with a label:

- `hot`: 75+
- `usable`: 55-74.99
- `skip`: below 55

## Components

Each component has raw input, normalized subscore, weight, and weighted contribution.

| Component | Intent |
| --- | --- |
| `engagement_quality` | Combined quality from likes, comments, shares relative to views. |
| `freshness` | Recent videos score higher. |
| `views_normalized` | Log-normalized view count. |
| `like_rate` | Like/view quality. |
| `comment_share_quality` | Comment and share signal quality. |
| `duration_fit` | Rewards short-form durations that are easier to process. |
| `speech_bonus` | Rewards videos with speech signal when known. |
| `text_complexity_penalty` | Penalizes high text density. |
| `watermark_penalty` | Penalizes heavy watermark signals. |
| `copyright_risk_penalty` | Penalizes high copyright risk flags. |

## Tuning

Weights live in `ScoreWeights`. Presets can provide different weights without changing the core formula.

Example: `viral_discovery` weights engagement/freshness more heavily, while `safe_reup` gives more weight to duration fit, speech, low text complexity, watermark, and copyright risk.

## Why Deterministic

Phase 1 needs a score an operator can trust and debug. No AI judgment is hidden inside the score. Later AI analysis can add better input signals, but the final score remains explainable.

## Current Limits

- No true growth velocity yet because only latest metric snapshots are used in this step.
- No semantic product fit analysis yet.
- Watermark/text/speech signals are optional until analysis pipelines exist.

