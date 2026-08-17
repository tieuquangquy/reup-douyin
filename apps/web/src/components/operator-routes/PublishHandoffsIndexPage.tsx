"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchPublishHandoffs } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { humanizeStatus } from "../../lib/statusLabels";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { PublishHandoff, PublishHandoffStatus } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime } from "../ops-console/OpsShared";
import { IntelligenceTableSkeleton } from "./IntelligenceDataSkeleton";

type StageFilter = "all" | PublishHandoffStatus;

export function PublishHandoffsIndexPage() {
  const t = useT();
  const [handoffs, setHandoffs] = useState<PublishHandoff[]>([]);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [stageFilter, setStageFilter] = useState<StageFilter>("all");
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = loadedAt ? "refresh" : "initial";
    try {
      await request.run(
        () => fetchPublishHandoffs(100),
        (payload) => {
          setHandoffs(payload.items);
          setLoadedAt(new Date().toISOString());
        },
        mode
      );
      if (mode === "refresh") {
        notify({ id: "publish-handoffs-refresh", message: t("opsPublishHandoffs.refreshSuccess"), tone: "success" });
      }
    } catch (err) {
      if (mode === "refresh") {
        notify({
          id: "publish-handoffs-refresh",
          message: err instanceof Error ? err.message : t("opsPublishHandoffs.loadError"),
          tone: "error"
        });
      }
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const needsAttention = useMemo(
    () => handoffs.filter((item) => item.status === "FAILED_NEEDS_ATTENTION"),
    [handoffs]
  );
  const attentionCount = needsAttention.length;
  const readyCount = handoffs.filter((item) => item.status === "READY_FOR_OPERATOR").length;
  const acceptedCount = handoffs.filter((item) => item.status === "ACCEPTED").length;
  const draftCount = handoffs.filter((item) => item.status === "DRAFT").length;
  const cancelledCount = handoffs.filter((item) => item.status === "CANCELLED").length;
  const platformCount = useMemo(
    () => new Set(handoffs.map((item) => item.target_platform)).size,
    [handoffs]
  );
  const packageCount = useMemo(
    () => new Set(handoffs.map((item) => item.export_package_id)).size,
    [handoffs]
  );

  const visibleHandoffs = useMemo(() => {
    if (stageFilter === "all") return handoffs;
    return handoffs.filter((item) => item.status === stageFilter);
  }, [handoffs, stageFilter]);

  const mixSlices: Array<{ key: PublishHandoffStatus; label: string; count: number; tone: string }> = [
    {
      key: "FAILED_NEEDS_ATTENTION",
      label: t("opsPublishHandoffs.needsAttention"),
      count: attentionCount,
      tone:
        attentionCount > 0
          ? `${handoffStageClass("FAILED_NEEDS_ATTENTION")} is-warning`
          : handoffStageClass("FAILED_NEEDS_ATTENTION")
    },
    {
      key: "READY_FOR_OPERATOR",
      label: t("opsPublishHandoffs.stageReady"),
      count: readyCount,
      tone: handoffStageClass("READY_FOR_OPERATOR")
    },
    {
      key: "ACCEPTED",
      label: t("opsPublishHandoffs.stageAccepted"),
      count: acceptedCount,
      tone: handoffStageClass("ACCEPTED")
    },
    {
      key: "DRAFT",
      label: t("opsPublishHandoffs.stageDraft"),
      count: draftCount,
      tone: handoffStageClass("DRAFT")
    },
    {
      key: "CANCELLED",
      label: t("opsPublishHandoffs.stageCancelled"),
      count: cancelledCount,
      tone: handoffStageClass("CANCELLED")
    }
  ];

  const mixSignals: Array<{
    key: string;
    label: string;
    detail: string;
    count: number;
    tone: string;
    filter?: StageFilter;
  }> = [
    {
      key: "attention",
      label: t("opsPublishHandoffs.needsAttention"),
      detail: t("opsPublishHandoffs.needsAttentionDetail"),
      count: attentionCount,
      tone:
        attentionCount > 0
          ? `${handoffStageClass("FAILED_NEEDS_ATTENTION")} is-warning`
          : handoffStageClass("FAILED_NEEDS_ATTENTION"),
      filter: "FAILED_NEEDS_ATTENTION"
    },
    {
      key: "ready",
      label: t("opsPublishHandoffs.ready"),
      detail: t("opsPublishHandoffs.readyDetail"),
      count: readyCount,
      tone: handoffStageClass("READY_FOR_OPERATOR"),
      filter: "READY_FOR_OPERATOR"
    },
    {
      key: "platforms",
      label: t("opsPublishHandoffs.platforms"),
      detail: t("opsPublishHandoffs.platformsDetail"),
      count: platformCount,
      tone: "is-platforms"
    },
    {
      key: "packages",
      label: t("opsPublishHandoffs.packagesLinked"),
      detail: t("opsPublishHandoffs.packagesLinkedDetail"),
      count: packageCount,
      tone: "is-packages"
    }
  ];

  const mixDenom = Math.max(handoffs.length, 1);
  const attentionDeg = (attentionCount / mixDenom) * 360;
  const readyDeg = (readyCount / mixDenom) * 360;
  const acceptedDeg = (acceptedCount / mixDenom) * 360;
  const draftDeg = (draftCount / mixDenom) * 360;
  const cancelledDeg = (cancelledCount / mixDenom) * 360;
  const a1 = attentionDeg;
  const a2 = a1 + readyDeg;
  const a3 = a2 + acceptedDeg;
  const a4 = a3 + draftDeg;
  const a5 = a4 + cancelledDeg;
  const donutGradient =
    handoffs.length === 0
      ? "conic-gradient(#d5e0db 0deg 90deg, #c5d4ce 90deg 180deg, #b7c7c0 180deg 270deg, #a9bab3 270deg 360deg)"
      : `conic-gradient(#c4841a 0deg ${a1}deg, #2f8f6f ${a1}deg ${a2}deg, #4f6fbf ${a2}deg ${a3}deg, #8aa39a ${a3}deg ${a4}deg, #9aaba3 ${a4}deg ${a5}deg, #d5e0db ${a5}deg 360deg)`;

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  const shellProps = {
    actions: refreshAction,
    description: t("opsPublishHandoffs.description"),
    title: t("opsPublishHandoffs.title")
  } as const;

  const status = !loadedAt && !request.error ? "loading" : request.error && !loadedAt ? "error" : "success";
  const skeleton = <IntelligenceTableSkeleton label={t("opsPublishHandoffs.loadingDetail")} rows={7} />;

  const rail = (
    <header className="publish-handoffs-rail">
      <div className="publish-handoffs-rail__copy">
        <strong>{t("opsPublishHandoffs.handoffRecords")}</strong>
        {loadedAt ? (
          <em>
            {t("opsPublishHandoffs.loadedAt")}
            {" · "}
            <time dateTime={loadedAt}>{formatRailLoadedAt(loadedAt)}</time>
          </em>
        ) : null}
      </div>
      <nav className="publish-handoffs-rail__links" aria-label={t("opsPublishHandoffs.triage")}>
        <Link className="publish-handoffs-rail__link" href="/publishing/export-packages">
          <HandoffBayIcon kind="packages" />
          <span>{t("opsPublishHandoffs.openPackages")}</span>
        </Link>
        <Link className="publish-handoffs-rail__link" href="/selection/reup-queue">
          <HandoffBayIcon kind="queue" />
          <span>{t("opsPublishHandoffs.openReupQueue")}</span>
        </Link>
      </nav>
    </header>
  );

  const mixPanel =
    status === "success" ? (
      <aside aria-label={t("opsPublishHandoffs.stageFilter")} className="publish-handoffs-mix">
        <div className="publish-handoffs-mix__board">
          <div className="publish-handoffs-mix__stage" role="tablist">
            <button
              aria-label={t("opsPublishHandoffs.filterAll")}
              aria-selected={stageFilter === "all"}
              className={`publish-handoffs-mix__donut${handoffs.length === 0 ? " is-empty" : ""}${
                stageFilter === "all" ? " is-current" : ""
              }`.trim()}
              onClick={() => setStageFilter("all")}
              role="tab"
              style={{ background: donutGradient }}
              type="button"
            >
              <span className="publish-handoffs-mix__donut-core">
                <b>{handoffs.length}</b>
                <small>{t("opsPublishHandoffs.filterAll")}</small>
              </span>
            </button>
            <ul className="publish-handoffs-mix__legend">
              {mixSlices.map((slice) => {
                const pct = Math.round((slice.count / mixDenom) * 100);
                return (
                  <li key={slice.key}>
                    <button
                      aria-selected={stageFilter === slice.key}
                      className={`publish-handoffs-mix__legend-item ${slice.tone}${slice.count === 0 ? " is-empty" : ""}${
                        stageFilter === slice.key ? " is-current" : ""
                      }`.trim()}
                      onClick={() => setStageFilter(slice.key)}
                      role="tab"
                      type="button"
                    >
                      <i aria-hidden="true" />
                      <span>{slice.label}</span>
                      <em>{pct}%</em>
                      <b>{slice.count}</b>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          <div aria-label={t("opsPublishHandoffs.spectrumSignals")} className="publish-handoffs-mix__signals">
            {mixSignals.map((signal) => {
              const active = signal.filter != null && stageFilter === signal.filter;
              const className = `publish-handoffs-mix__signal ${signal.tone}${signal.count === 0 ? " is-empty" : ""}${
                active ? " is-current" : ""
              }`.trim();
              if (signal.filter) {
                return (
                  <button
                    aria-pressed={active}
                    className={className}
                    key={signal.key}
                    onClick={() => setStageFilter(signal.filter!)}
                    type="button"
                  >
                    <span>{signal.label}</span>
                    <strong>{signal.count}</strong>
                    <em>{signal.detail}</em>
                  </button>
                );
              }
              return (
                <div className={className} key={signal.key}>
                  <span>{signal.label}</span>
                  <strong>{signal.count}</strong>
                  <em>{signal.detail}</em>
                </div>
              );
            })}
          </div>
        </div>
      </aside>
    ) : (
      <aside aria-hidden="true" className={`publish-handoffs-mix is-${status}`}>
        <div className="publish-handoffs-mix__board">
          <div className="publish-handoffs-mix__stage">
            <div className="publish-handoffs-mix__donut is-placeholder">
              <span className="publish-handoffs-mix__donut-core">
                <b>—</b>
                <small>{t("opsPublishHandoffs.filterAll")}</small>
              </span>
            </div>
            <ul className="publish-handoffs-mix__legend is-placeholder">
              {mixSlices.map((slice) => (
                <li key={slice.key}>
                  <span className={`publish-handoffs-mix__legend-item ${slice.tone} is-empty`}>
                    <i aria-hidden="true" />
                    <span>{slice.label}</span>
                    <em>—</em>
                    <b>—</b>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="publish-handoffs-mix__signals is-placeholder">
            {mixSignals.map((signal) => (
              <div className={`publish-handoffs-mix__signal ${signal.tone} is-empty`} key={signal.key}>
                <span>{signal.label}</span>
                <strong>—</strong>
                <em>{signal.detail}</em>
              </div>
            ))}
          </div>
        </div>
      </aside>
    );

  const dockContent =
    status === "success" ? (
      <>
        {needsAttention.length > 0 ? (
          <section aria-label={t("opsPublishHandoffs.attention")} className="publish-handoffs-attention">
            <strong>{t("opsPublishHandoffs.attention")}</strong>
            <span>{needsAttention.length}</span>
            <p>{t("opsPublishHandoffs.needsAttentionDetail")}</p>
            <button
              className="publish-handoffs-attention__jump"
              onClick={() => setStageFilter("FAILED_NEEDS_ATTENTION")}
              type="button"
            >
              {t("opsPublishHandoffs.filterAttention")}
            </button>
          </section>
        ) : null}
        {handoffs.length === 0 ? (
          <div className="publish-handoffs-empty">
            <strong>{t("opsPublishHandoffs.empty")}</strong>
          </div>
        ) : visibleHandoffs.length === 0 ? (
          <div className="publish-handoffs-empty">
            <strong>{t("opsPublishHandoffs.filterEmpty")}</strong>
          </div>
        ) : (
          <ul className="publish-handoffs-manifest">
            {visibleHandoffs.map((item) => (
              <HandoffSlip item={item} key={item.id} t={t} />
            ))}
          </ul>
        )}
        <p className="publish-handoffs-footnote">{t("opsPublishHandoffs.noPlatformApi")}</p>
      </>
    ) : (
      <span />
    );

  return (
    <OperatorStudioShell {...shellProps}>
      <main className="publish-handoffs-page is-bay">
        <div className="publish-handoffs-bay">
          {rail}
          <div className="publish-handoffs-bay__body">
            {mixPanel}
            <section aria-label={t("opsPublishHandoffs.handoffs")} className="publish-handoffs-dock">
              <AsyncContentBoundary
                errorState={
                  <OpsState
                    title={t("opsPublishHandoffs.unavailableTitle")}
                    detail={request.error?.message ?? t("opsPublishHandoffs.loadError")}
                    retry={() => void load()}
                  />
                }
                loadingLabel={t("opsPublishHandoffs.loadingDetail")}
                refreshing={request.refreshing}
                skeleton={skeleton}
                status={status}
              >
                {dockContent}
              </AsyncContentBoundary>
            </section>
          </div>
        </div>
      </main>
    </OperatorStudioShell>
  );
}

function handoffStageClass(status: string): string {
  if (status === "FAILED_NEEDS_ATTENTION") return "is-attention";
  if (status === "READY_FOR_OPERATOR") return "is-ready";
  if (status === "ACCEPTED") return "is-accepted";
  if (status === "CANCELLED") return "is-cancelled";
  return "is-draft";
}

function formatRailLoadedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function HandoffBayIcon({ kind }: { kind: "packages" | "queue" }) {
  if (kind === "queue") {
    return (
      <svg aria-hidden="true" className="publish-handoffs-rail__link-icon" fill="none" viewBox="0 0 20 20">
        <path d="M4.5 6.2h11M4.5 10h11M4.5 13.8h7.2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="publish-handoffs-rail__link-icon" fill="none" viewBox="0 0 20 20">
      <path
        d="M5.2 5.2h9.6a1.4 1.4 0 0 1 1.4 1.4v7.8a1.4 1.4 0 0 1-1.4 1.4H5.2a1.4 1.4 0 0 1-1.4-1.4V6.6a1.4 1.4 0 0 1 1.4-1.4Z"
        stroke="currentColor"
        strokeWidth="1.55"
      />
      <path d="M7.1 8.4h5.8M7.1 11h3.8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
    </svg>
  );
}

function HandoffSlip({ item, t }: { item: PublishHandoff; t: (key: string) => string }) {
  const stage = handoffStageClass(item.status);
  const title = `${t("opsPublishHandoffs.handoff")} ${item.id.slice(0, 8)}`;
  const platformLabel = item.target_platform.replace(/_/g, " ");
  return (
    <li>
      <Link
        aria-label={`${t("opsPublishHandoffs.open")}: ${title}`}
        className={`publish-handoffs-manifest__slip ${stage}`.trim()}
        href={`/publishing/publish-handoffs/${item.id}`}
      >
        <span aria-hidden="true" className="publish-handoffs-manifest__stamp" />
        <div className="publish-handoffs-manifest__identity">
          <strong className="publish-handoffs-manifest__title" title={item.id}>
            {title}
          </strong>
          <p className="publish-handoffs-manifest__meta">
            <span>{platformLabel}</span>
            <span aria-hidden="true">·</span>
            <time dateTime={item.ready_at ?? item.created_at}>{formatDateTime(item.ready_at ?? item.created_at)}</time>
          </p>
        </div>
        <div className="publish-handoffs-manifest__seals" aria-hidden="true">
          <em title={item.export_package_id}>
            {t("opsPublishHandoffs.package")} {item.export_package_id.slice(0, 8)}
          </em>
        </div>
        <div className="publish-handoffs-manifest__signal">
          <span className={`publish-handoffs-chip ${stage}`}>{humanizeStatus(item.status)}</span>
          <span aria-hidden="true" className="publish-handoffs-manifest__open">
            <svg className="publish-handoffs-manifest__open-icon" fill="none" viewBox="0 0 20 20">
              <path d="m7.5 4.5 5 5.5-5 5.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
            </svg>
          </span>
        </div>
      </Link>
    </li>
  );
}
