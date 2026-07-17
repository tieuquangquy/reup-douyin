# Douyin Capture Inbox UX Redesign User Guide

## Overview

Douyin Capture Inbox is the staging workspace for items captured by the browser extension. Use it to understand what was captured, fix incomplete rows, skip duplicates or failures, and promote ready items to Review Board.

## Opening The Workspace

Open `/ops/extensions/douyin/capture-inbox` from the Ops Console or from the Douyin Extension Manager capture result.

## Header Actions

- Promote ready items: promotes ready items to Review Board.
- Open source profile: opens the submitted profile or captured page when available.
- Refresh session: reloads the current capture session.
- Go to Review Board: opens the canonical review surface for promoted candidates.

## Summary Cards

Use the summary cards to understand and filter the current session:

- Captured: all captured rows.
- Ready: items ready to promote.
- Duplicates: items already known or duplicated.
- Needs enrichment: items that need enrichment or preview work.
- Failed: items that need retry or exclusion.
- Promoted: items already sent to Review Board.

Click a summary card to filter the list.

## Search, Filters, And Sorting

- Search by caption, video id, source URL, or status.
- Use chips for All, Ready, Duplicate, Needs action, Failed, and Promoted.
- Sort by Newest, Ready first, or Needs action first.

## Item Cards

Collapsed cards are intentionally simple. They show:

- thumbnail/cover;
- caption snippet;
- status badge;
- short source/video identifier;
- duration and posted date if captured;
- recommended next action;
- contextual buttons for that item state.

Technical metadata and diagnostics are available in the right-side detail panel instead of the main list.

## Detail Panel

Select an item to inspect details. The panel includes:

- Overview;
- Source;
- Metadata;
- Media / Preview;
- Diagnostics.

Diagnostics are collapsed by default and should only be opened when troubleshooting.

## Batch Actions

Select multiple items to show the sticky batch bar. Available safe actions include:

- Promote selected;
- Retry selected;
- Exclude selected;
- Clear selection.

## Recommended Next Action

The banner near the top summarizes the most useful next step, such as promoting ready items, ignoring duplicates, or retrying failed enrichment.

## Safety Notes

- Capture Inbox does not publish videos.
- Capture Inbox does not replace Review Board.
- Missing data is rendered honestly as `Not captured`, `Pending`, or `Not analyzed yet`.
- Raw diagnostics are hidden until explicitly opened.
