"use client";

import { useEffect, useState } from "react";
import { useT } from "../../lib/i18n";
import { fetchPublishDraft } from "../../lib/api";
import type { PublishDraft } from "../../types/publish-draft";
import { OperatorPublishDraftPage } from "./OperatorPublishDraftPage";

export function PublishDraftByIdPage({ draftId }: { draftId: string }) {
  const t = useT();
  const [draft, setDraft] = useState<PublishDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setDraft(await fetchPublishDraft(draftId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publishDraftById.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [draftId, load]);

  if (loading) return <div className="state-panel skeleton">{t("publishDraftById.loading")}</div>;

  if (error || !draft) {
    return (
      <div className="state-panel">
        <h1>{t("publishDraftById.couldNotLoad")}</h1>
        <p>{error ?? t("publishDraftById.draftNotFound")}</p>
        <button type="button" onClick={() => void load()}>{t("publishDraftById.retry")}</button>
      </div>
    );
  }

  return <OperatorPublishDraftPage initialDraftId={draft.id} sourceVideoId={draft.source_video_id} />;
}
