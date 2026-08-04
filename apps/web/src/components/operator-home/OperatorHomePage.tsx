"use client";

import { useEffect, useState } from "react";

import { fetchOperatorHomeSummary } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { OperatorHomeSummaryResponse } from "../../types/operations";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OperatorHomeCommandCenter } from "./OperatorHomeCommandCenter";
import { OperatorHomeLoadingSkeleton } from "./OperatorHomeShared";

export function OperatorHomePage() {
  const t = useT();
  const [summary, setSummary] = useState<OperatorHomeSummaryResponse | null>(null);
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = summary ? "refresh" : "initial";
    try {
      const result = await request.run(fetchOperatorHomeSummary, setSummary, mode);
      if (mode === "refresh" && result) {
        notify({ id: "home-refresh", message: "Home refreshed.", tone: "success" });
      }
    } catch (err) {
      if (mode === "refresh") {
        notify({
          id: "home-refresh",
          message: err instanceof Error ? err.message : t("operatorHome.loadError"),
          tone: "error"
        });
      }
    }
  }

  useEffect(() => {
    void load();
    // Load once; operator refresh is explicit so active-work context stays stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshAction = (
    <TopbarRefreshButton
      busy={request.refreshing}
      disabled={request.initialLoading}
      onClick={() => void load()}
    />
  );

  return (
    <OperatorStudioShell actions={refreshAction} description={t("home.description")} title={t("home.title")}>
      <AsyncContentBoundary
        errorState={
          <div className="operator-home-v2-load-error">
            <h1>{t("operatorHome.couldNotLoad")}</h1>
            <p>{request.error?.message}</p>
            <button onClick={() => void load()} type="button">{t("common.retry")}</button>
          </div>
        }
        refreshing={request.refreshing}
        skeleton={<OperatorHomeLoadingSkeleton />}
        status={!summary ? (request.error ? "error" : "loading") : "success"}
      >
        {summary ? <OperatorHomeCommandCenter summary={summary} /> : null}
      </AsyncContentBoundary>
    </OperatorStudioShell>
  );
}
