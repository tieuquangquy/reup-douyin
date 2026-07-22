"use client";

import { useT } from "../../lib/i18n";
import type { EditableSegment, TranscriptValidationWarning } from "../../types/transcript-editor";
import type { TtsClipFit } from "../../types/tts";
import { formatMs, formatTranslationAuthorityChip, resolveTranslationAuthority } from "../../lib/transcriptEditorState";
import { flagToneClassName, resolveSegmentCompareState } from "../../lib/transcriptEditorPresentation";
import {
  classifyTtsFitTone,
  formatTtsFitRatio,
  ttsFitStatusKey
} from "../../lib/ttsFitPresentation";
import { TranscriptSegmentFlags } from "./TranscriptSegmentFlags";
import { TranscriptSegmentTimingEditor } from "./TranscriptSegmentTimingEditor";

type SegmentOpsIconKind = "play" | "pause" | "split" | "merge-prev" | "merge-next" | "reset";

function SegmentOpsIcon({ kind }: { kind: SegmentOpsIconKind }) {
  if (kind === "play") {
    return (
      <svg className="segment-ops__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M7 5.2v9.6L15 10 7 5.2z" fill="currentColor" />
      </svg>
    );
  }
  if (kind === "pause") {
    return (
      <svg className="segment-ops__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M6.2 5h2.4v10H6.2V5Zm5.2 0h2.4v10h-2.4V5Z" fill="currentColor" />
      </svg>
    );
  }
  if (kind === "split") {
    return (
      <svg className="segment-ops__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M10 4.5v11M6.2 8.2 10 4.5l3.8 3.7M6.2 11.8 10 15.5l3.8-3.7"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "merge-prev") {
    return (
      <svg className="segment-ops__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M15.5 10H6.2M9.5 6.5 6 10l3.5 3.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "merge-next") {
    return (
      <svg className="segment-ops__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 10h9.3M10.5 6.5 14 10l-3.5 3.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg className="segment-ops__icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M15.2 9.2a5.2 5.2 0 1 1-1.5-3.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        d="M15.2 4.5v3.5h-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

type Props = {
  segment: EditableSegment;
  sourceVideoId: string;
  analysisVersion: string | null;
  translationPreset: string | null;
  allSegments: EditableSegment[];
  warnings: TranscriptValidationWarning[];
  canMergePrevious: boolean;
  canMergeNext: boolean;
  ttsClipFit?: TtsClipFit | null;
  onChange: (patch: Partial<Pick<EditableSegment, "sourceText" | "translatedText" | "startMs" | "endMs" | "status">>) => void;
  isPlaying?: boolean;
  onPlay: () => void;
  onMergePrevious: () => void;
  onMergeNext: () => void;
  onSplit: () => void;
  onReset: () => void;
};

export function TranscriptFocusEditor({
  segment,
  sourceVideoId,
  analysisVersion,
  translationPreset,
  allSegments,
  warnings,
  canMergePrevious,
  canMergeNext,
  ttsClipFit = null,
  onChange,
  isPlaying = false,
  onPlay,
  onMergePrevious,
  onMergeNext,
  onSplit,
  onReset
}: Props) {
  const t = useT();
  const flags = [...segment.difficultyFlags, ...segment.qualityFlags];
  const compare = resolveSegmentCompareState(segment);
  const authority = formatTranslationAuthorityChip(resolveTranslationAuthority(allSegments));
  const cardWarnings = warnings.filter(
    (warning) =>
      ["empty_source_text", "negative_timing", "invalid_timing", "overlapping_timing", "awkward_short_segment"].includes(
        warning.code
      ) ||
      warning.code.includes("low_confidence") ||
      warning.code.includes("likely_mistranscribed")
  );
  const rangeLabel = `${formatMs(segment.startMs)} – ${formatMs(segment.endMs)}`;
  const fitStatusKey = ttsFitStatusKey(ttsClipFit?.fit_status);
  const fitRatio = formatTtsFitRatio(ttsClipFit?.fit_ratio ?? null);

  return (
    <section className="transcript-focus-editor transcript-focus-editor--dual" aria-label={t("transcriptEditorBench.focusLabel")}>
      <header className="transcript-focus-chrome">
        <div className="transcript-focus-chrome__head">
          <h2 className="transcript-focus-chrome__title">
            {t("transcriptEditorBench.segmentTitle").replace("{index}", String(segment.segmentIndex))}
            {segment.isDirty ? <span className="dirty-dot">{t("transcriptEditorRow.edited")}</span> : null}
          </h2>
          <p className="transcript-focus-chrome__range">{rangeLabel}</p>
        </div>

        <details className="transcript-focus-chrome__run">
          <summary>{t("transcriptEditorBench.runDetails")}</summary>
          <div className="transcript-focus-chrome__run-body">
            <span className="transcript-focus-editor__job-id">{sourceVideoId}</span>
            {analysisVersion ? <span className="pill">{analysisVersion}</span> : null}
            {translationPreset ? <span className="pill">{translationPreset}</span> : null}
            {authority ? (
              <span className="pill good translation-authority-chip" title={t("transcriptEditorHeader.translationAuthorityHint")}>
                {authority}
              </span>
            ) : null}
          </div>
        </details>

        <div className="transcript-focus-chrome__toolbar">
          <TranscriptSegmentTimingEditor
            startMs={segment.startMs}
            endMs={segment.endMs}
            onChange={(patch) => onChange(patch)}
          />
          <div className="transcript-focus-editor__actions segment-ops">
            <button
              type="button"
              className={`segment-ops__btn segment-ops__btn--play${isPlaying ? " is-playing" : ""}`}
              aria-pressed={isPlaying}
              onClick={onPlay}
            >
              <SegmentOpsIcon kind={isPlaying ? "pause" : "play"} />
              <span>{t(isPlaying ? "transcriptEditorRow.pause" : "transcriptEditorRow.play")}</span>
            </button>
            <button type="button" className="segment-ops__btn" onClick={onSplit}>
              <SegmentOpsIcon kind="split" />
              <span>{t("transcriptEditorRow.split")}</span>
            </button>
            <button type="button" className="segment-ops__btn" disabled={!canMergePrevious} onClick={onMergePrevious}>
              <SegmentOpsIcon kind="merge-prev" />
              <span>{t("transcriptEditorRow.mergePrev")}</span>
            </button>
            <button type="button" className="segment-ops__btn" disabled={!canMergeNext} onClick={onMergeNext}>
              <SegmentOpsIcon kind="merge-next" />
              <span>{t("transcriptEditorRow.mergeNext")}</span>
            </button>
            <button type="button" className="segment-ops__btn" onClick={onReset} disabled={!segment.isDirty}>
              <SegmentOpsIcon kind="reset" />
              <span>{t("transcriptEditorRow.reset")}</span>
            </button>
          </div>
        </div>
      </header>

      <div className="transcript-dual-pane">
        <label className="transcript-dual-pane__zh">
          <span className="transcript-dual-pane__tab is-active">{t("transcriptEditorBench.originalChinese")}</span>
          <textarea
            className="source-textarea-primary"
            value={segment.sourceText}
            onChange={(event) => onChange({ sourceText: event.target.value })}
            placeholder={t("transcriptEditorBench.zhPlaceholder")}
            title={t("transcriptEditorRow.sourcePrimaryHint")}
          />
          {!compare.sourceUnchanged ? (
            <span className="transcript-focus-editor__dirty-hint">{t("transcriptEditorBench.changedFromSaved")}</span>
          ) : null}
        </label>
        <label className="transcript-dual-pane__vi">
          <span className="transcript-dual-pane__tab-row">
            <span className="transcript-dual-pane__tab is-active">{t("transcriptEditorBench.translatedVietnamese")}</span>
            {segment.translatedText.trim() ? (
              <span className="transcript-dual-pane__badge">{t("transcriptEditorBench.translatedBadge")}</span>
            ) : null}
          </span>
          <textarea
            className="translation-textarea"
            value={segment.translatedText}
            onChange={(event) => onChange({ translatedText: event.target.value })}
            placeholder={t("transcriptEditorBench.viPlaceholder")}
          />
          {!compare.vietnameseUnchanged ? (
            <span className="transcript-focus-editor__dirty-hint">{t("transcriptEditorBench.changedFromSaved")}</span>
          ) : null}
        </label>
      </div>

      <div className="segment-meta">
        {ttsClipFit?.fit_status ? (
          <div className="transcript-tts-fit" aria-label={t("transcriptEditorTts.fitLabel")}>
            <span className={flagToneClassName(classifyTtsFitTone(ttsClipFit.fit_status))}>
              {t(`transcriptEditorTts.fitStatus.${fitStatusKey}`)}
              {fitRatio ? ` · ${fitRatio}` : ""}
            </span>
            {fitStatusKey !== "fits_well" && fitStatusKey !== "unknown" ? (
              <p className="transcript-tts-fit__hint">{t(`transcriptEditorTts.fitHint.${fitStatusKey}`)}</p>
            ) : null}
          </div>
        ) : null}
        <TranscriptSegmentFlags flags={flags} mode="summary" />
      </div>

      {cardWarnings.length > 0 ? (
        <ul className="segment-warnings">
          {cardWarnings.map((warning) => (
            <li key={`${warning.segmentId}-${warning.code}`}>{warning.label}</li>
          ))}
        </ul>
      ) : null}

      {flags.length > 0 ? (
        <details className="compare-machine-details">
          <summary>
            <span className="compare-machine-details__title">{t("transcriptEditorCompare.machineDetails")}</span>
            <span className="compare-machine-details__hint">{t("transcriptEditorCompare.machineDetailsHint")}</span>
          </summary>
          <div className="compare-machine-details__body">
            <TranscriptSegmentFlags flags={flags} mode="all" operatorQuiet={false} />
          </div>
        </details>
      ) : null}
    </section>
  );
}
