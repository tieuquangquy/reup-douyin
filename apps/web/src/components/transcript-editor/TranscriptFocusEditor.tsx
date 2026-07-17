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
            <button type="button" className="segment-ops__btn segment-ops__btn--play" onClick={onPlay}>
              {t("transcriptEditorRow.play")}
            </button>
            <button type="button" className="segment-ops__btn" onClick={onSplit}>
              {t("transcriptEditorRow.split")}
            </button>
            <button type="button" className="segment-ops__btn" disabled={!canMergePrevious} onClick={onMergePrevious}>
              {t("transcriptEditorRow.mergePrev")}
            </button>
            <button type="button" className="segment-ops__btn" disabled={!canMergeNext} onClick={onMergeNext}>
              {t("transcriptEditorRow.mergeNext")}
            </button>
            <button type="button" className="segment-ops__btn" onClick={onReset} disabled={!segment.isDirty}>
              {t("transcriptEditorRow.reset")}
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
