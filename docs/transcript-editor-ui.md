# Transcript Editor UI

The transcript editor is the checkpoint between audio analysis and TTS/subtitle generation. It lets the operator fix only weak AI output instead of rewriting the whole script.

## Route

```text
/source-videos/[id]/transcript-editor
```

The route loads current transcript and translation draft rows for one `SourceVideo`.

## Layout

- Header: video identifier, analysis version, translation preset, segment count, flagged count, unsaved count, save/discard/rerun actions.
- Media preview: simple video preview from the source URL and jump-to-current-segment support.
- Segment list: fast inline editing for timing, source text, and Vietnamese draft.
- Compare panel: selected segment before/after timing, source text, translation text, flags, and warnings.
- Floating action bar: appears when there are unsaved edits or validation warnings.
- Timing blockers: negative, invalid, or overlapping timing disables save until fixed.

The layout is optimized for desktop. It remains usable on narrow screens, but phase 1 prioritizes long operator review sessions on a PC.

## Segment Row

Each row shows:

- segment index
- start/end time and duration
- source text
- translated text
- confidence
- speaker label when available
- difficulty and quality flags
- dirty state
- play, merge, split, reset actions

Translated text is visually emphasized because it feeds TTS and subtitles in the next step.

## Save / Discard / Rerun

- Save draft sends changed existing segments to `PUT /source-videos/{id}/transcript-draft`.
- Discard restores the latest loaded draft in browser state.
- Rerun calls `POST /source-videos/{id}/translation-draft/rerun` and creates an `ANALYZE_AUDIO` job.
- The browser warns on navigation when there are unsaved edits.
- Save is allowed with soft warnings, but blocked for invalid timing because step 10 needs a coherent timeline.

## Merge / Split Strategy

Phase 1 keeps merge/split simple:

- Merge adjacent segments by combining text, translation, timing, and flags. The second segment is archived server-side with `is_current = false`.
- Split uses midpoint timing and simple text midpoint splitting. Operator can adjust text and timing immediately after reload.
- The backend does not aggressively renumber existing segments during phase 1; UI sorts by timing.
- Merge buttons are disabled at list boundaries. If unsaved edits exist, the UI asks for confirmation because server merge reloads the saved draft.

This avoids fragile timeline rewrites while giving operators the operations they need most.

## Warnings

The editor surfaces:

- `low_confidence_source`
- `translation_too_long_for_slot`
- `awkward_short_segment`
- `overlapping_timing`
- `missing_translation`
- `empty_source_text`
- unresolved review or provider flags

Warnings are operator guidance, not blockers. Save remains possible so the operator can checkpoint partial work.

Hard timing issues are blockers:

- negative start time
- end time before or equal to start time
- overlap with a neighboring current segment

## Data Flow

```text
GET transcript
GET translation draft
GET audio-analysis summary
  -> build editable state
  -> inline edit / compare / validate
  -> PUT transcript draft
  -> reload current rows
```

Merge/split use dedicated backend endpoints because they change row lifecycle, not only field values.

## Phase 1 Limits

- No waveform editor.
- No frame-level precision.
- No TTS generation.
- No subtitle render.
- No OCR editor.
- No collaborative editing or auth.
