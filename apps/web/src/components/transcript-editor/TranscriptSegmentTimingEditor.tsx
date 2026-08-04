"use client";

import { useEffect, useState } from "react";
import { useT } from "../../lib/i18n";
import { formatMs, formatTimingSeconds, parseTimingTimecodeToMs } from "../../lib/transcriptEditorState";

type Props = {
  startMs: number;
  endMs: number;
  onChange: (patch: { startMs?: number; endMs?: number }) => void;
};

export function TranscriptSegmentTimingEditor({ startMs, endMs, onChange }: Props) {
  const t = useT();
  const durationSec = formatTimingSeconds(Math.max(0, endMs - startMs), 1);
  const [startDraft, setStartDraft] = useState(() => formatMs(startMs));
  const [endDraft, setEndDraft] = useState(() => formatMs(endMs));

  useEffect(() => {
    setStartDraft(formatMs(startMs));
  }, [startMs]);

  useEffect(() => {
    setEndDraft(formatMs(endMs));
  }, [endMs]);

  function commitStart(raw: string) {
    const ms = parseTimingTimecodeToMs(raw);
    if (ms == null) {
      setStartDraft(formatMs(startMs));
      return;
    }
    onChange({ startMs: ms });
    setStartDraft(formatMs(ms));
  }

  function commitEnd(raw: string) {
    const ms = parseTimingTimecodeToMs(raw);
    if (ms == null) {
      setEndDraft(formatMs(endMs));
      return;
    }
    onChange({ endMs: ms });
    setEndDraft(formatMs(ms));
  }

  return (
    <div className="timing-editor timing-editor--compact timing-editor--timecode">
      <div className="timing-editor__range timing-editor__range--timecode">
        <input
          type="text"
          className="timing-editor__field"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          aria-label={t("transcriptEditorTiming.start")}
          value={startDraft}
          onChange={(event) => {
            const next = event.target.value;
            setStartDraft(next);
            const ms = parseTimingTimecodeToMs(next);
            if (ms != null) onChange({ startMs: ms });
          }}
          onBlur={() => commitStart(startDraft)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.currentTarget.blur();
            }
          }}
        />
        <span className="timing-editor__sep timing-editor__sep--arrow" aria-hidden="true">
          →
        </span>
        <input
          type="text"
          className="timing-editor__field"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          aria-label={t("transcriptEditorTiming.end")}
          value={endDraft}
          onChange={(event) => {
            const next = event.target.value;
            setEndDraft(next);
            const ms = parseTimingTimecodeToMs(next);
            if (ms != null) onChange({ endMs: ms });
          }}
          onBlur={() => commitEnd(endDraft)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.currentTarget.blur();
            }
          }}
        />
        <span className="timing-editor__duration" title={formatMs(endMs - startMs)}>
          {t("transcriptEditorTiming.duration").replace("{seconds}", durationSec)}
        </span>
      </div>
    </div>
  );
}
