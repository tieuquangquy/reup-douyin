# Douyin Capture Inbox Right-side Sticky Inspector User Guide

## Overview

Capture Inbox uses a right-side sticky inspector on desktop so operators can inspect captured Douyin items without scrolling to the bottom of the page.

The media gallery remains visible in the main workspace, while item details update on the right.

## Desktop Layout

The top of the page keeps the existing Capture Inbox controls:

- compact header,
- Session Ribbon,
- Status Strip,
- Studio filter toolbar.

Below the controls, the workspace is split:

- left/main area: Media-first Tile Gallery and batch action bar,
- right area: sticky item inspector.

## Inspecting an Item

1. Click a tile thumbnail, title, or `Details` action.
2. The tile becomes visually active.
3. The right inspector updates immediately with that item.
4. Click another tile to update the same inspector.
5. Use `Close details` to clear the active inspector state.

## Empty Inspector State

When no item is selected, the right inspector shows:

- title: `Item details`
- message: `Select an item to inspect details.`

This keeps the review area calm and avoids showing a blank panel.

## Inspector Sections

The right inspector is structured for quick scanning:

1. Overview
2. Source / References
3. Metadata
4. Outputs / Downstream artifacts
5. Diagnostics
6. Raw details

Diagnostics and raw details are secondary and collapsed by default.

## Long Text

Long title, caption, description, transcript-like text, notes, and raw text are clamped by default in the overview. Use `Show more` and `Show less` when more text is needed.

Raw payload details remain available in secondary disclosure sections.

## Delete, Filters, and Session Changes

- If the active item is deleted, the inspector closes safely.
- If the active session is deleted or changed, stale inspector state is cleared or re-resolved safely.
- If filters hide the active item, the inspector clears so it stays aligned with the visible triage set.

## Narrow Screens

On narrow screens, the right inspector may behave like a sheet or bottom sheet so it fits the viewport. This is a responsive fallback only. Desktop remains a main gallery plus right-side sticky inspector.

## Implementation Status

Implemented and verified:

- the desktop details surface is `RightInspector` in the right-side workspace column,
- the old bottom `InspectorSheet` primary desktop pattern is removed,
- source tests for right-inspector behavior pass,
- web typecheck passes.
