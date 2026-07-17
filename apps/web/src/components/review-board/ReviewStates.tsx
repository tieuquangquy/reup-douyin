"use client";

import { useT } from "../../lib/i18n";

export function LoadingState() {
  return (
    <div className="candidate-grid">
      <div className="candidate-card skeleton" />
      <div className="candidate-card skeleton" />
      <div className="candidate-card skeleton" />
    </div>
  );
}

export function EmptyState() {
  const t = useT();
  return (
    <div className="state-panel">
      <h2>{t("reviewBoardPage.noCandidatesMatch")}</h2>
      <p>{t("reviewBoardPage.noCandidatesMatchBody")}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useT();
  return (
    <div className="state-panel">
      <h2>{t("reviewBoardPage.couldNotLoad")}</h2>
      <p>{message}</p>
      <button className="primary" onClick={onRetry}>{t("reviewBoardPage.retry")}</button>
    </div>
  );
}
