# Caption, CTA, And Hashtag Drafts

Publish metadata is editable by the operator and stored as structured fields on `PublishDraft`.

## Caption

Canonical field:

- `caption`

Support metadata:

- `caption_draft_json`
- `generation_source`

Phase 1 generates a short deterministic caption from `SourceVideo.caption` or the source video external id. This is only a starting point for operator editing.

## CTA

Canonical field:

- `cta_text`

Support metadata:

- `cta_draft_json`

Each target platform has a default CTA in the publish target registry. The operator can edit it independently from the caption.

## Hashtags

Canonical field:

- `hashtags_json`

Shape:

```json
[
  { "tag": "vietsub", "source": "platform_default" },
  { "tag": "douyinfood", "source": "source_profile" }
]
```

The UI edits hashtags as a tag list, not as one raw text string. This makes platform validation and connector formatting easier later.

## Platform Target Defaults

Phase 1 supports placeholder targets:

- `TIKTOK`
- `FACEBOOK_REELS`
- `YOUTUBE_SHORTS`

The target registry defines:

- label
- caption length limit
- hashtag limit
- default CTA
- default hashtags
- account reference requirement placeholder

No platform connector logic lives in the UI.

## Validation

`mark-ready` requires:

- target platform
- non-empty caption
- non-empty CTA
- at least one hashtag
- hashtag count within target limit
- post text within target caption limit
- source video is `PUBLISH_READY`
- render output is `APPROVED`

## Phase 1 Limits

- No AI caption generator.
- No platform-specific compliance checks beyond basic limits.
- No OAuth or account linking.
- No auto-posting.
