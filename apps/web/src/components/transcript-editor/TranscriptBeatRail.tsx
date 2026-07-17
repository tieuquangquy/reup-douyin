"use client";

import { useT } from "../../lib/i18n";
import type { EditableSegment } from "../../types/transcript-editor";
import type { TtsClipFit } from "../../types/tts";
import { formatMs } from "../../lib/transcriptEditorState";
import { flagToneClassName } from "../../lib/transcriptEditorPresentation";
import {
  beatRailShowsTtsFit,
  classifyTtsFitTone,
  formatTtsFitRatio,
  ttsFitStatusKey
} from "../../lib/ttsFitPresentation";

type Props = {
  segments: EditableSegment[];
  selectedSegmentId: string | null;
  onSelect: (segmentId: string) => void;
  clipFitsByTranslationId?: Map<string, TtsClipFit>;
};

export function TranscriptBeatRail({
  segments,
  selectedSegmentId,
  onSelect,
  clipFitsByTranslationId
}: Props) {
  const t = useT();
  return (
    <nav className="transcript-beat-rail" aria-label={t("transcriptEditorBench.beatRailLabel")}>
      <p className="transcript-beat-rail__label">{t("transcriptEditorBench.segmentsList")}</p>
      <ul className="transcript-beat-rail__list">
        {segments.map((segment) => {
          const selected = segment.localId === selectedSegmentId;
          const clip = segment.translationId
            ? clipFitsByTranslationId?.get(segment.translationId)
            : undefined;
          const showFit = beatRailShowsTtsFit(clip);
          const statusKey = ttsFitStatusKey(clip?.fit_status);
          const ratio = formatTtsFitRatio(clip?.fit_ratio ?? null);
          return (
            <li key={segment.localId}>
              <button
                type="button"
                className={`transcript-beat-rail__item${selected ? " is-selected" : ""}${segment.isDirty ? " is-dirty" : ""}`}
                onClick={() => onSelect(segment.localId)}
              >
                <span className="transcript-beat-rail__title">
                  {t("transcriptEditorBench.segmentLabel").replace("{index}", String(segment.segmentIndex))}
                </span>
                <span className="transcript-beat-rail__range">
                  [{formatMs(segment.startMs)} – {formatMs(segment.endMs)}]
                </span>
                {segment.isDirty ? (
                  <span className="transcript-beat-rail__dirty">{t("transcriptEditorRow.edited")}</span>
                ) : null}
                {showFit && clip ? (
                  <span
                    className={`${flagToneClassName(classifyTtsFitTone(clip.fit_status))} transcript-beat-rail__tts-fit`}
                    title={t(`transcriptEditorTts.fitHint.${statusKey}`)}
                  >
                    {t(`transcriptEditorTts.fitShort.${statusKey}`)}
                    {ratio ? ` ${ratio}` : ""}
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
