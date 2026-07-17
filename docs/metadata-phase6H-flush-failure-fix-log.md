# Phase 6H Flush Failure Fix Log

## Problem

Full Modal Harvest could:

- detect current aweme correctly
- extract duration/metrics correctly
- store a pending item locally

but flush still failed with `Failed to fetch`, leaving:

- `Pending > 0`
- `Flushed = 0`
- `Updated = 0`

## Root cause

The full-modal flush path was using `fetch()` directly from the Douyin content script.

That is a different execution boundary from the popup/backend calls that already worked. The popup calls the backend from extension UI context; the content script was trying to call the local backend directly from the page-attached execution path.

This made the flush path fragile and capable of failing before the backend ever received the request.

## Fix strategy

- route flush HTTP through the extension background runtime
- keep the content script as harvest controller owner
- persist flush diagnostics into progress/state
- make popup success/error messaging reflect actual flush result

## Scope

- `apps/extension-douyin-capture`
- tiny backend log/route test updates only
