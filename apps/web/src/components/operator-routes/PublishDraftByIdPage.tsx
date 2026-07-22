"use client";

import { useEffect, useState } from "react";
import { useT } from "../../lib/i18n";
import { fetchPublishDraft } from "../../lib/api";
import { useLatestRequest, type LatestRequestMode } from "../../lib/useLatestRequest";
import type { PublishDraft } from "../../types/publish-draft";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { OperatorPublishDraftPage } from "./OperatorPublishDraftPage";

export function PublishDraftByIdPage({ draftId }: { draftId: string }) {
  const t = useT();
  const [draft, setDraft] = useState<PublishDraft | null>(null);
  const request = useLatestRequest();

  async function load(mode: LatestRequestMode = "initial") {
    if (mode === "initial") setDraft(null);
    await request.run(
      async () => fetchPublishDraft(draftId),
      setDraft,
      mode
    ).catch(() => undefined);
  }

  useEffect(() => {
    void load();
  }, [draftId, t]);

  const boundaryStatus = request.initialLoading && !draft ? "loading" : request.error && !draft ? "error" : draft ? "success" : "empty";

  return (
    <AsyncContentBoundary
      refreshing={request.refreshing}
      status={boundaryStatus}
      skeletonVariant="detail"
      loadingLabel={t("publishDraftById.loading")}
      errorState={
        <div className="state-panel">
          <h1>{t("publishDraftById.couldNotLoad")}</h1>
          <p>{request.error?.message ?? t("publishDraftById.draftNotFound")}</p>
          <button type="button" onClick={() => void load("initial")}>{t("publishDraftById.retry")}</button>
        </div>
      }
    >
      {draft ? <OperatorPublishDraftPage initialDraftId={draft.id} sourceVideoId={draft.source_video_id} /> : null}
    </AsyncContentBoundary>
  );
}
