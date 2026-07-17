"use client";

type Props = {
  score: number | null;
  label: string | null;
  t: (key: string) => string;
};

export function CandidateScoreBadge({ score, label, t }: Props) {
  return (
    <div className="score-badge">
      <strong>{score == null ? "--" : Math.round(score)}</strong>
      <span>{label ?? t("reviewBoardPage.unscored")}</span>
    </div>
  );
}
