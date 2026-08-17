"use client";

import { useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { PublishDraftPage, type PublishDraftPageHandle } from "../publish-draft/PublishDraftPage";

export function OperatorPublishDraftPage({
  sourceVideoId,
  initialDraftId
}: {
  sourceVideoId: string;
  initialDraftId?: string;
}) {
  const t = useT();
  const pageRef = useRef<PublishDraftPageHandle>(null);
  const [refreshing, setRefreshing] = useState(false);

  return (
    <OperatorStudioShell
      actions={
        <TopbarRefreshButton
          busy={refreshing}
          onClick={() => {
            void (async () => {
              setRefreshing(true);
              try {
                await pageRef.current?.refresh();
              } finally {
                setRefreshing(false);
              }
            })();
          }}
        />
      }
      description={t("operatorRoutes.publishDraftDesc")}
      title={t("operatorRoutes.publishDraftTitle")}
    >
      <PublishDraftPage ref={pageRef} initialDraftId={initialDraftId} sourceVideoId={sourceVideoId} />
    </OperatorStudioShell>
  );
}
