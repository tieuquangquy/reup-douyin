# Phase 18I Canonical Run Harvest Batch Checkpoint Resume

This note describes resume semantics for canonical Whole Profile Harvest.

## Resume source

Resume reads only the canonical `douyinWholeProfileHarvest` state. It does not read V2 staged harvest state, legacy harvest state, pending flush queue state, or content-script safe-runner state.

## Resume queue

Resume processes queue entries that are still `pending`, plus `failed` entries with fewer than three attempts. Completed `updated` entries are not rebuilt or reprocessed during resume.

## Captcha pause

When captcha, security check, login checkpoint, or abnormal traffic is detected, harvest writes `status: paused`, `phase: harvest_paused_captcha`, `harvest.status: paused`, and `harvest.paused_reason: captcha_detected`.

The operator must solve the checkpoint manually in the Douyin tab. Resume then continues the canonical queue from durable state.

## Stop behavior

Stop writes `harvest.stop_requested: true` and pauses the canonical run. A later Resume clears the stop flag and continues retryable pending work from canonical state.

## Failure behavior

Hard payload/schema/security failures stop the canonical run as failed. Transient backend flush failures are checkpointed per target and the batch may complete with warnings so resume can retry the failed target later.
