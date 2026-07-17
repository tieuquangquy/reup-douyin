"use client";

import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { ReviewBoardPage } from "../review-board/ReviewBoardPage";

export function OperatorReviewBoardPage() {
  const t = useT();
  return (
    <OperatorStudioShell
      actions={
        <>
          <a href="/">{t("common.home")}</a>
          <a href="/production/downloads">{t("nav.productionWork")}</a>
          <a href="/publishing/drafts">{t("common.drafts")}</a>
        </>
      }
      description={t("operatorRoutes.reviewBoardDesc")}
      title={t("operatorRoutes.reviewBoardTitle")}
    >
      <ReviewBoardPage />
    </OperatorStudioShell>
  );
}
