"use client";

import { useT } from "../../lib/i18n";
import type { EditableSegment, TranscriptValidationWarning } from "../../types/transcript-editor";
import { formatMs } from "../../lib/transcriptEditorState";
import { TranscriptSegmentFlags } from "./TranscriptSegmentFlags";
import { TranscriptSegmentTimingEditor } from "./TranscriptSegmentTimingEditor";

type Props = {
  segment: EditableSegment;
  selected: boolean;
  warnings: TranscriptValidationWarning[];
  canMergePrevious: boolean;
  canMergeNext: boolean;
  onSelect: () => void;
  onChange: (patch: Partial<Pick<EditableSegment, "sourceText" | "translatedText" | "startMs" | "endMs" | "status">>) => void;
  onPlay: () => void;
  onMergePrevious: () => void;
  onMergeNext: () => void;
  onSplit: () => void;
  onReset: () => void;
};

export function TranscriptSegmentRow({
  segment,
  selected,
  warnings,
  canMergePrevious,
  canMergeNext,
  onSelect,
  onChange,
  onPlay,
  onMergePrevious,
  onMergeNext,
  onSplit,
  onReset
}: Props) {
  const t = useT();
  const flags = [...segment.difficultyFlags, ...segment.qualityFlags];
  // Only show timing/empty-source style warnings on the card — not machine review spam.
  const cardWarnings = warnings.filter((warning) =>
    ["empty_source_text", "negative_timing", "invalid_timing", "overlapping_timing", "awkward_short_segment"].includes(
      warning.code
    ) || warning.code.includes("low_confidence") || warning.code.includes("likely_mistranscribed")
  );

  return (
    <article
      className={`segment-row${selected ? " selected" : ""}${segment.isDirty ? " dirty" : ""}`}
      onClick={onSelect}
    >
      <div className="segment-row__head">
        <div className="segment-row__title">
          <strong>#{segment.segmentIndex}</strong>
          <span className="segment-row__range">
            {formatMs(segment.startMs)} – {formatMs(segment.endMs)}
          </span>
          {segment.isDirty ? <span className="dirty-dot">{t("transcriptEditorRow.edited")}</span> : null}
        </div>
        <div className="segment-row__actions">
          <button
            className="segment-row__action-primary"
            onClick={(event) => {
              event.stopPropagation();
              onPlay();
            }}
          >
            {t("transcriptEditorRow.play")}
          </button>
          <button
            disabled={!canMergePrevious}
            onClick={(event) => {
              event.stopPropagation();
              onMergePrevious();
            }}
          >
            {t("transcriptEditorRow.mergePrev")}
          </button>
          <button
            disabled={!canMergeNext}
            onClick={(event) => {
              event.stopPropagation();
              onMergeNext();
            }}
          >
            {t("transcriptEditorRow.mergeNext")}
          </button>
          <button
            onClick={(event) => {
              event.stopPropagation();
              onSplit();
            }}
          >
            {t("transcriptEditorRow.split")}
          </button>
          <button
            onClick={(event) => {
              event.stopPropagation();
              onReset();
            }}
            disabled={!segment.isDirty}
          >
            {t("transcriptEditorRow.reset")}
          </button>
        </div>
      </div>

      <TranscriptSegmentTimingEditor
        startMs={segment.startMs}
        endMs={segment.endMs}
        onChange={(patch) => onChange(patch)}
      />

      <div className="segment-edit-grid segment-edit-grid--zh-first">
        <label className="segment-source-field">
          {t("transcriptEditorRow.sourceTextPrimary")}
          <textarea
            className="source-textarea-primary"
            value={segment.sourceText}
            onChange={(event) => onChange({ sourceText: event.target.value })}
            title={t("transcriptEditorRow.sourcePrimaryHint")}
          />
        </label>
        <label className="segment-vi-field">
          {t("transcriptEditorRow.vietnameseDraft")}
          <textarea
            className="translation-textarea"
            value={segment.translatedText}
            onChange={(event) => onChange({ translatedText: event.target.value })}
          />
        </label>
      </div>

      <div className="segment-meta">
        <TranscriptSegmentFlags flags={flags} mode="summary" />
      </div>

      {cardWarnings.length > 0 ? (
        <ul className="segment-warnings">
          {cardWarnings.map((warning) => (
            <li key={`${warning.segmentId}-${warning.code}`}>{warning.label}</li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
