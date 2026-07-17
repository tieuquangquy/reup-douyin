# Douyin Thumbnail Mapping Fix User Guide

## What This Fix Changes

Capture Inbox thumbnails will appear when the captured Douyin page payload already contains a usable image source, such as a card cover image, poster image, or known thumbnail URL field.

The UI will continue to show `No thumbnail available` when no truthful image exists in the captured data.

## Operator Workflow

1. Open Douyin in the supported browser with the local extension installed.
2. Capture the current profile/feed page through the extension flow.
3. Open Capture Inbox.
4. Review cards:
   - If the source page exposed a usable thumbnail image, the card should show it.
   - If not, the card shows an honest placeholder.
5. Open the item detail drawer to inspect the thumbnail link and raw diagnostics.

## Expected Thumbnail Sources

The system can use existing image data such as:

- `thumbnail_url`
- `poster_url`
- `cover_url`
- `cover`
- `poster`
- `origin_cover`
- `dynamic_cover`
- `animated_cover`
- image-like entries in `url_list`
- nearby DOM images or video posters captured by the extension

## What This Fix Does Not Do

- It does not download videos.
- It does not generate screenshots.
- It does not create fake placeholder art.
- It does not bypass Douyin privacy/challenge restrictions.
- It does not implement a full media pipeline.

## Verified Behavior

The implementation was verified with extension typecheck/extractor tests, web typecheck/Capture Inbox tests, and API unittest coverage for thumbnail alias preservation and deterministic backend canonicalization.

## Troubleshooting

If a card still says `No thumbnail available`:

1. Open the item detail drawer.
2. Expand diagnostics.
3. Check whether `raw_payload_json` contains an image-like thumbnail, poster, cover, or image URL.
4. If no such source exists, the placeholder is expected and truthful.
5. If a usable image source exists in raw diagnostics but the card does not show it, that is a mapping bug and should be fixed in resolver priority.

## Limitations

Douyin may lazy-load, obfuscate, or omit image URLs from the visible DOM. This fix only uses image sources already available in the extension payload or downstream metadata. It does not perform additional crawling or media extraction.
