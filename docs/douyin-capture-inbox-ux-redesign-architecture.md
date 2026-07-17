# Douyin Capture Inbox UX Redesign Architecture

## Purpose

This UX redesign turns Capture Inbox into an operator-first staging workspace. It keeps the existing capture/session/item data model and focuses on clearer presentation, safer actions, and reduced cognitive load.

## Boundary

Capture Inbox remains the staging surface between browser extension capture and Review Board promotion.

Canonical workflow remains:

1. Douyin browser extension captures a page.
2. API stores a Capture Session and Captured Items.
3. Operator reviews staged items in Capture Inbox.
4. Operator promotes ready items to Review Board.
5. Review Board receives canonical `VideoCandidate` records only.
6. Approved candidates move downstream to Reup Queue.

## UI Structure

### Header

The header presents:

- title: Douyin Capture Inbox;
- current session id/status;
- current profile/page context;
- primary action: Promote ready items;
- secondary actions: Open source profile, Refresh session, Go to Review Board.

### Summary Row

Clickable cards provide both overview and filtering:

- Captured;
- Ready;
- Duplicates;
- Needs enrichment;
- Failed;
- Promoted.

### Filter/Search Row

Operators can narrow the workspace with:

- free-text search;
- chips for All, Ready, Duplicate, Needs action, Failed, and Promoted;
- sorting by Newest, Ready first, and Needs action first.

### Main List

Collapsed cards show only operational information:

- thumbnail/cover;
- caption/title snippet;
- status badge;
- short source URL or video id;
- duration/date when available;
- next action text;
- contextual action buttons.

Raw payloads, raw diagnostics, and dense metadata do not appear in collapsed cards.

### Detail Panel

The right-side panel contains:

- Overview;
- Source;
- Metadata;
- Media / Preview;
- Diagnostics.

Diagnostics stay collapsed by default.

### Batch Actions

A sticky batch action bar appears when multiple items are selected. It supports safe workflows:

- Promote selected;
- Retry selected;
- Exclude selected;
- Clear selection.

Actions are disabled or absent when they are not relevant to the selected item states.

## State Vocabulary

The UI maps raw item statuses to operator-facing badges:

- Ready;
- Duplicate;
- Needs enrichment;
- Failed;
- Promoted;
- Preview pending.

## Contextual Action Matrix

- Ready: Preview, Details, Promote.
- Duplicate: Open existing, Details, Dismiss.
- Needs enrichment: Retry enrich, Retry preview, Details.
- Failed: View error, Retry, Exclude.
- Promoted: Open candidate, View details.
- Preview pending: Retry preview, Details.

## Metadata Honesty

Missing values must not be shown as fake zeroes. Preferred labels:

- Not captured.
- Pending.
- Not analyzed yet.
- Not promoted.
- Not marked duplicate.

## Testing Strategy

Focused source-level tests verify that the required UX affordances remain present without introducing browser automation or live Douyin dependencies.
