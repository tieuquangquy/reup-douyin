"use client";

import { useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { FinalReviewPage, type FinalReviewPageHandle } from "../final-review/FinalReviewPage";

export function OperatorFinalReviewPage({ sourceVideoId }: { sourceVideoId: string }) {
  const t = useT();
  const pageRef = useRef<FinalReviewPageHandle>(null);
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
      description={t("operatorRoutes.finalReviewDesc")}
      title={t("operatorRoutes.finalReviewTitle")}
    >
      <FinalReviewPage ref={pageRef} sourceVideoId={sourceVideoId} />
    </OperatorStudioShell>
  );
}
