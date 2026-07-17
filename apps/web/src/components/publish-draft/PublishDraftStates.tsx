"use client";

import { useT } from "../../lib/i18n";

export function PublishDraftLoadingState() {
  const t = useT();
  return (
    <main className="publish-page">
      <div className="state-panel">
        <h2>{t("publishDraftStates.loading")}</h2>
        <p>{t("publishDraftStates.loadingBody")}</p>
      </div>
    </main>
  );
}

export function PublishDraftErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const t = useT();
  return (
    <main className="publish-page">
      <div className="state-panel">
        <h2>{t("publishDraftStates.error")}</h2>
        <p>{message}</p>
        <button className="primary" onClick={onRetry}>{t("publishDraftStates.retry")}</button>
      </div>
    </main>
  );
}
