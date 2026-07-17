# Reup Export Handoff User Guide

## Overview

The Export Package and Publish Handoff workflow helps an operator move approved, media-ready Reup Queue items into an inspectable downstream package without automatically publishing anything.

Use this flow after an item reaches `READY_TO_EXPORT` in Reup Queue.

## Operator Workflow

1. Open Reup Queue at `/selection/reup-queue`.
2. Filter to `READY_TO_EXPORT` or select eligible items from the grouped queue view.
3. Select one or more queue items.
4. Choose the batch action to create an Export Package.
5. Review the batch result for created, skipped, and failed items.
6. Open the Export Package detail page from the batch result, from package metadata on a queue item, or from `/publishing/export-packages`.
7. Inspect package contents, source video references, render/publish draft references if present, and diagnostics.
8. Create a Publish Handoff from the package when ready.
9. Open the Publish Handoff detail page from the package page, from queue item metadata, or from `/publishing/publish-handoffs`.
10. Continue manual publishing or future downstream publish workflows outside this slice.

## Batch Actions

The Reup Queue batch panel supports state-aware operations:

- Start processing.
- Hold.
- Resume.
- Retry.
- Cancel.
- Mark media ready.
- Create Export Package.
- Create Publish Handoff.

Each batch action reports which selected items succeeded, were skipped, or failed. Skipped items include safe reason codes such as ineligible state or missing readiness.

## Export Package Pages

- Export Package index: `/publishing/export-packages`.
- Export Package detail: `/publishing/export-packages/[packageId]`.

The package detail view shows:

- package status.
- package label and notes.
- item count.
- source video ids.
- queue item ids.
- render output ids when available.
- publish draft ids when available.
- readiness diagnostics.
- package manifest preview.

## Publish Handoff Pages

- Publish Handoff index: `/publishing/publish-handoffs`.
- Publish Handoff detail: `/publishing/publish-handoffs/[handoffId]`.

The handoff detail view shows:

- handoff status.
- target platform.
- linked Export Package.
- payload preview.
- diagnostics.
- created/ready timestamps.

A Publish Handoff is not an external publication and does not mean the video has been uploaded.

## Interpreting Results

- `READY_TO_EXPORT` means media prep is complete enough to start packaging.
- `EXPORT_PACKAGE_CREATED` means the item is linked to a durable package.
- `READY_TO_PUBLISH` means the item is packaged and can proceed to handoff.
- `PUBLISH_HANDOFF_CREATED` means an inspectable handoff exists.
- `FAILED_NEEDS_ATTENTION` means an operator-visible issue must be resolved.
- `CANCELLED` means the item or downstream record is no longer active.

## Safety Notes

- The workflow never publishes automatically.
- The UI does not show secrets, cookies, or platform credentials.
- Missing render or publish draft references are shown as diagnostics instead of hidden failures unless required by a specific action.
- Package and handoff records are durable so future workers can resume or consume them safely.
