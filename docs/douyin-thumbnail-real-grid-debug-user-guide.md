# Douyin Thumbnail Real Grid Debug User Guide

## Purpose

This guide explains how to verify that visible Douyin profile card-grid thumbnails are captured into Capture Inbox as real images.

## Expected Behavior

When a Douyin profile grid shows visible video poster cards:

1. Use the Douyin capture extension on the profile page.
2. The extension extracts visible video cards and their real image sources.
3. The backend stores the selected image as `thumbnail_url`.
4. Capture Inbox displays the thumbnail image in the media tile.
5. If no real image source exists in the DOM, Capture Inbox shows the truthful `No thumbnail` placeholder.

## What Counts As A Supported Thumbnail Source

The extraction pipeline should support real image sources from:

- image `src`
- raw image `src` attributes
- `data-src`
- image-like dataset fields
- `srcset`
- video poster attributes
- inline CSS `background-image`
- computed CSS `background-image`

## How To Inspect A Failed Capture

1. In Capture Inbox, open the item detail panel.
2. Check the `Thumbnail` field.
3. If it says `Not captured`, inspect the diagnostic/raw payload section.
4. Look for thumbnail-like fields in `raw_payload_json`, such as:
   - `thumbnail_url`
   - `cover_url`
   - `poster_url`
   - `url_list`
5. If raw payload has an image URL but the tile still shows no thumbnail, the issue is likely in backend normalization or frontend resolver logic.
6. If raw payload has no image URL, the issue is likely in extension DOM extraction or capture timing.

## Expected Debug Evidence

After the hard-fix, safe logs and retained payload fields help identify the stage:

- Extension diagnostics: how many videos had thumbnail candidates, total candidate count, and source pattern labels.
- Backend receive log: whether incoming videos included thumbnail candidates.
- Backend persist/normalize log: whether canonical `thumbnail_url` was selected per item.
- API response fields: whether response items include `thumbnail_url`, `preview_url`, and `raw_payload_json` evidence.
- Frontend non-production resolver log: whether resolver received and selected `item.thumbnail_url`.

## Verification Commands

The focused verification commands used for this hard-fix were:

- `npm --workspace @reup-douyin/extension-douyin-capture run test` from the repository root.
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- `npx tsx apps/web/src/test/capture-inbox.test.ts` from the repository root.

A root-level API command, `python -m unittest apps.api.tests.test_douyin_extension_capture_service`, fails because the API tests import `src` relative to `apps/api`; rerun the API command from `apps/api` as shown above.

## Limitations

- Douyin may change DOM structure, class names, lazy-loading behavior, or image delivery hosts.
- The extension only captures sources present in the page DOM at capture time.
- The pipeline does not download or generate thumbnails; it only preserves real image URLs found in the DOM/payload.
- If the profile grid has not finished rendering or images are not yet materialized in DOM attributes/styles, capture may still have no real thumbnail source.

## Safety Notes

- Do not paste cookies, tokens, or account credentials into issue reports.
- Share only sanitized payload snippets showing field names, source types, and redacted URLs when needed.
