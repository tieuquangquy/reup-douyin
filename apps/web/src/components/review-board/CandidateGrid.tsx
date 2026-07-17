"use client";

import { useT } from "../../lib/i18n";
import type { BulkActionStatus, Candidate } from "../../types/review-board";
import { CandidateCard } from "./CandidateCard";

type Props = {
  candidates: Candidate[];
  selectedIds: Set<string>;
  onToggleSelection: (candidateId: string) => void;
  onOpenDetails: (candidate: Candidate) => void;
  onQuickStatus: (candidate: Candidate, status: BulkActionStatus) => void;
};

export function CandidateGrid({
  candidates,
  selectedIds,
  onToggleSelection,
  onOpenDetails,
  onQuickStatus
}: Props) {
  const t = useT();
  return (
    <div className="candidate-grid">
      {candidates.map((candidate) => (
        <CandidateCard
          key={candidate.id}
          candidate={candidate}
          selected={selectedIds.has(candidate.id)}
          onToggleSelection={() => onToggleSelection(candidate.id)}
          onOpenDetails={() => onOpenDetails(candidate)}
          onKeep={() => onQuickStatus(candidate, "APPROVED")}
          onReject={() => onQuickStatus(candidate, "REJECTED")}
          t={t}
        />
      ))}
    </div>
  );
}
