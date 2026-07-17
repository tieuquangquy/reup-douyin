"use client";

import { useT } from "../../lib/i18n";
import {
  classifyFlagTone,
  flagToneClassName,
  formatFlagLabel,
  partitionSegmentFlags
} from "../../lib/transcriptEditorPresentation";

type Props = {
  flags: string[];
  /** summary = quiet operator chips; all = full list when not quiet. */
  mode?: "summary" | "all";
  maxVisible?: number;
  /** When false, include pipeline/noise (debug). Default quiet. */
  operatorQuiet?: boolean;
};

export function TranscriptSegmentFlags({
  flags,
  mode = "all",
  maxVisible = 3,
  operatorQuiet = true
}: Props) {
  const t = useT();
  const uniqueFlags = Array.from(new Set(flags.filter(Boolean)));
  if (uniqueFlags.length === 0) {
    return null;
  }

  const limit = mode === "all" && !operatorQuiet ? uniqueFlags.length : maxVisible;
  const { visible, overflowCount, pipeline } = partitionSegmentFlags(uniqueFlags, limit, {
    operatorQuiet
  });

  if (visible.length === 0 && pipeline.length === 0) {
    return null;
  }

  if (!operatorQuiet) {
    return (
      <div className="segment-flags segment-flags--machine">
        {visible.length > 0 ? (
          <div className="segment-flags__group segment-flags__group--attention">
            <span className="segment-flags__group-label">{t("transcriptEditorFlags.attention")}</span>
            <div className="segment-flags__chips">
              {visible.map((flag) => (
                <span className={flagToneClassName(classifyFlagTone(flag))} key={flag}>
                  {formatFlagLabel(flag)}
                </span>
              ))}
              {overflowCount > 0 ? (
                <span className="pill segment-flags__more">
                  {t("transcriptEditorFlags.moreFlags").replace("{count}", String(overflowCount))}
                </span>
              ) : null}
            </div>
          </div>
        ) : null}
        {pipeline.length > 0 ? (
          <div className="segment-flags__group segment-flags__group--pipeline">
            <span className="segment-flags__group-label">{t("transcriptEditorFlags.pipeline")}</span>
            <div className="segment-flags__chips">
              {pipeline.map((flag) => (
                <span className={`${flagToneClassName(classifyFlagTone(flag))} segment-flags__chip--pipeline`} key={flag}>
                  {formatFlagLabel(flag)}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={`segment-flags${mode === "summary" ? " segment-flags--summary" : ""}`}>
      {visible.map((flag) => (
        <span className={flagToneClassName(classifyFlagTone(flag))} key={flag}>
          {formatFlagLabel(flag)}
        </span>
      ))}
      {overflowCount > 0 ? (
        <span className="pill segment-flags__more">
          {t("transcriptEditorFlags.moreFlags").replace("{count}", String(overflowCount))}
        </span>
      ) : null}
    </div>
  );
}
