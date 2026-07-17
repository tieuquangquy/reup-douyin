import { useT } from "../../lib/i18n";
import { formatMs } from "../../lib/transcriptEditorState";

type Props = {
  startMs: number;
  endMs: number;
  onChange: (patch: { startMs?: number; endMs?: number }) => void;
};

export function TranscriptSegmentTimingEditor({ startMs, endMs, onChange }: Props) {
  const t = useT();
  const durationSec = ((endMs - startMs) / 1000).toFixed(1);

  return (
    <div className="timing-editor timing-editor--compact">
      <label>
        {t("transcriptEditorTiming.start")}
        <input
          type="number"
          min="0"
          step="0.1"
          value={(startMs / 1000).toFixed(2)}
          onChange={(event) => onChange({ startMs: Math.round(Number(event.target.value) * 1000) })}
        />
      </label>
      <label>
        {t("transcriptEditorTiming.end")}
        <input
          type="number"
          min="0"
          step="0.1"
          value={(endMs / 1000).toFixed(2)}
          onChange={(event) => onChange({ endMs: Math.round(Number(event.target.value) * 1000) })}
        />
      </label>
      <span className="timing-editor__duration" title={formatMs(endMs - startMs)}>
        {t("transcriptEditorTiming.duration").replace("{seconds}", durationSec)}
      </span>
    </div>
  );
}
