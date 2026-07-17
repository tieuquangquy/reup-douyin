# Douyin Network-First Pipeline Fix User Guide

## What changes for the operator

The Capture Inbox should present Douyin profile-grid captures with clearer, more truthful metadata:

- Thumbnails come from canonical captured poster/cover URLs when available.
- Portrait Douyin posters are displayed without misleading 16:9 cropping.
- Duration, posted date, views, likes, and comments use canonical captured fields first.
- Status labels are separated into Preview, Source link, and Media asset.

## Status label meanings

- Preview Ready: a real thumbnail/preview image URL was captured.
- Preview Missing: no real thumbnail/preview image URL was captured.
- Source link Captured: a source video URL or share URL exists.
- Source link Missing: no source/share URL exists.
- Media asset Not generated: the system has not generated or downloaded an internal media asset.
- Media asset Ready: a downstream internal media asset exists.
- Media asset Failed: downstream media asset generation failed.

## Expected profile-grid behavior

For a normal visible Douyin profile-grid capture, the operator should expect:

- visible cards appear in the Capture Inbox,
- poster thumbnails render when the extension captured a real cover URL,
- source links are captured independently of media asset readiness,
- missing metadata is labeled honestly rather than shifted into another field.

## Evidence limitation for this fix

This implementation pass was authorized without real HAR/network JSON, extension payload, API response, screenshot, or logs. If a later real capture still shows incorrect values, collect one visible item across the following boundaries before further changes:

1. network JSON aweme item,
2. extension payload item,
3. backend/API response item,
4. visible UI card values.

Those four artifacts allow a precise item-level truth matrix and source-of-error diagnosis.

## Troubleshooting checklist

If thumbnails are still missing:

- Confirm the Douyin page was loaded before capture so network hooks had a chance to observe profile data.
- Confirm the item has `thumbnail_url` in the API response.
- Confirm `preview_status` is `ready` only when the thumbnail URL is real.
- If using direct execute fallback, expect DOM-only fallback behavior and weaker metadata.

If counts or posted values look shifted:

- Check whether the API response has canonical numeric fields.
- Do not rely on raw payload aliases as the normal UI source.
- Capture one real item evidence set before making further parsing changes.
