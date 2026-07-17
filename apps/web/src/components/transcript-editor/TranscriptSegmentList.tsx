import type { EditableSegment, TranscriptValidationWarning } from "../../types/transcript-editor";
import { TranscriptSegmentRow } from "./TranscriptSegmentRow";

type Props = {
  segments: EditableSegment[];
  selectedSegmentId: string | null;
  warnings: TranscriptValidationWarning[];
  onSelect: (segmentId: string) => void;
  onChange: (segmentId: string, patch: Partial<Pick<EditableSegment, "sourceText" | "translatedText" | "startMs" | "endMs" | "status">>) => void;
  onPlay: (segment: EditableSegment) => void;
  onMerge: (segmentId: string, direction: "previous" | "next") => void;
  onSplit: (segment: EditableSegment) => void;
  onReset: (segmentId: string) => void;
};

export function TranscriptSegmentList({
  segments,
  selectedSegmentId,
  warnings,
  onSelect,
  onChange,
  onPlay,
  onMerge,
  onSplit,
  onReset
}: Props) {
  return (
    <section className="segment-list" aria-label="Transcript segments">
      {segments.map((segment, index) => (
        <TranscriptSegmentRow
          key={segment.localId}
          segment={segment}
          selected={segment.localId === selectedSegmentId}
          warnings={warnings.filter((warning) => warning.segmentId === segment.localId)}
          canMergePrevious={index > 0}
          canMergeNext={index < segments.length - 1}
          onSelect={() => onSelect(segment.localId)}
          onChange={(patch) => onChange(segment.localId, patch)}
          onPlay={() => onPlay(segment)}
          onMergePrevious={() => onMerge(segment.localId, "previous")}
          onMergeNext={() => onMerge(segment.localId, "next")}
          onSplit={() => onSplit(segment)}
          onReset={() => onReset(segment.localId)}
        />
      ))}
    </section>
  );
}
