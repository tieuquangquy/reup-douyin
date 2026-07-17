"use client";

import { useT } from "../../lib/i18n";
import type { EditableSegment, TranscriptValidationWarning } from "../../types/transcript-editor";
import { formatMs } from "../../lib/transcriptEditorState";
import { resolveSegmentCompareState } from "../../lib/transcriptEditorPresentation";
import { TranscriptSegmentFlags } from "./TranscriptSegmentFlags";

type Props = {
  segment: EditableSegment | null;
  warnings: TranscriptValidationWarning[];
};

export function TranscriptComparePanel({ segment, warnings }: Props) {
  const t = useT();
  if (!segment) {
    return (
      <aside className="compare-panel">
        <h2>{t("transcriptEditorCompare.title")}</h2>
        <p className="compare-panel__empty">{t("transcriptEditorCompare.empty")}</p>
      </aside>
    );
  }

  const compare = resolveSegmentCompareState(segment);
  const flags = [...segment.difficultyFlags, ...segment.qualityFlags];
  const operatorWarnings = warnings.filter(
    (warning) =>
      ["empty_source_text", "negative_timing", "invalid_timing", "overlapping_timing"].includes(warning.code) ||
      warning.code.includes("low_confidence") ||
      warning.code.includes("likely_mistranscribed")
  );

  return (
    <aside className="compare-panel">
      <h2>
        {t("transcriptEditorCompare.title")} #{segment.segmentIndex}
      </h2>

      <div className="compare-block compare-block--primary">
        <h3>{t("transcriptEditorCompare.sourcePrimary")}</h3>
        {compare.sourceUnchanged ? (
          <>
            <p className="compare-no-diff">{t("transcriptEditorCompare.noChanges")}</p>
            <p className="after">{segment.sourceText || t("transcriptEditorCompare.emptyValue")}</p>
          </>
        ) : (
          <>
            <p className="compare-label">{t("transcriptEditorCompare.saved")}</p>
            <p className="before">{segment.originalSourceText || t("transcriptEditorCompare.emptyValue")}</p>
            <p className="compare-label">{t("transcriptEditorCompare.current")}</p>
            <p className="after">{segment.sourceText || t("transcriptEditorCompare.emptyValue")}</p>
          </>
        )}
      </div>

      <div className="compare-block">
        <h3>{t("transcriptEditorCompare.vietnamese")}</h3>
        {compare.vietnameseUnchanged ? (
          <>
            <p className="compare-no-diff">{t("transcriptEditorCompare.noChanges")}</p>
            <p className="before">{segment.translatedText || t("transcriptEditorCompare.emptyValue")}</p>
          </>
        ) : (
          <>
            <p className="compare-label">{t("transcriptEditorCompare.saved")}</p>
            <p className="before">{segment.originalTranslatedText || t("transcriptEditorCompare.emptyValue")}</p>
            <p className="compare-label">{t("transcriptEditorCompare.current")}</p>
            <p className="after">{segment.translatedText || t("transcriptEditorCompare.emptyValue")}</p>
          </>
        )}
      </div>

      <div className={`compare-block${compare.timingUnchanged ? "" : " compare-block--changed"}`}>
        <h3>{t("transcriptEditorCompare.timing")}</h3>
        {compare.timingUnchanged ? (
          <p className="compare-timing-same">
            {formatMs(segment.startMs)} – {formatMs(segment.endMs)}
          </p>
        ) : (
          <>
            <p>
              <span className="compare-label">{t("transcriptEditorCompare.saved")}: </span>
              {formatMs(segment.originalStartMs)} – {formatMs(segment.originalEndMs)}
            </p>
            <p>
              <span className="compare-label">{t("transcriptEditorCompare.current")}: </span>
              {formatMs(segment.startMs)} – {formatMs(segment.endMs)}
            </p>
          </>
        )}
      </div>

      {operatorWarnings.length > 0 ? (
        <div className="compare-block">
          <h3>{t("transcriptEditorCompare.warnings")}</h3>
          <ul className="compare-warnings">
            {operatorWarnings.map((warning) => (
              <li key={`${warning.segmentId}-${warning.code}`}>{warning.label}</li>
            ))}
          </ul>
        </div>
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
    </aside>
  );
}
