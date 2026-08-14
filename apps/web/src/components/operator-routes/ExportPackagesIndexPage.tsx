"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchExportPackages } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { humanizeStatus } from "../../lib/statusLabels";
import { useLatestRequest } from "../../lib/useLatestRequest";
import type { ExportPackage, ExportPackageStatus } from "../../types/export-handoff";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OpsState, formatDateTime } from "../ops-console/OpsShared";
import { IntelligenceTableSkeleton } from "./IntelligenceDataSkeleton";

type StageFilter = "all" | ExportPackageStatus;

export function ExportPackagesIndexPage() {
  const t = useT();
  const [packages, setPackages] = useState<ExportPackage[]>([]);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [stageFilter, setStageFilter] = useState<StageFilter>("all");
  const request = useLatestRequest();
  const { notify } = useNotice();

  async function load() {
    const mode = loadedAt ? "refresh" : "initial";
    try {
      await request.run(
        () => fetchExportPackages(100),
        (payload) => {
          setPackages(payload.items);
          setLoadedAt(new Date().toISOString());
        },
        mode,
      );
      if (mode === "refresh") notify({ id: "export-packages-refresh", message: "Export packages refreshed.", tone: "success" });
    } catch (err) {
      if (mode === "refresh") {
        notify({
          id: "export-packages-refresh",
          message: err instanceof Error ? err.message : t("opsExportPackages.loadError"),
          tone: "error",
        });
      }
    }
  }

  useEffect(() => {
    void load();
  }, [t]);

  const needsAttention = useMemo(
    () => packages.filter((item) => item.status === "FAILED_NEEDS_ATTENTION"),
    [packages],
  );
  const draftCount = packages.filter((item) => item.status === "DRAFT").length;
  const readyCount = packages.filter((item) => item.status === "READY_FOR_HANDOFF").length;
  const handedOffCount = packages.filter((item) => item.status === "HANDOFF_CREATED").length;
  const attentionCount = needsAttention.length;
  const linkedHandoffCount = packages.reduce((sum, item) => sum + item.publish_handoff_ids.length, 0);
  const itemsPackedCount = packages.reduce((sum, item) => sum + item.item_count, 0);
  const avgItemsPacked = packages.length === 0 ? 0 : Math.round(itemsPackedCount / packages.length);

  const visiblePackages = useMemo(() => {
    if (stageFilter === "all") return packages;
    return packages.filter((item) => item.status === stageFilter);
  }, [packages, stageFilter]);

  const mixSlices: Array<{ key: ExportPackageStatus; label: string; count: number; tone: string }> = [
    { key: "DRAFT", label: t("opsExportPackages.draftPackages"), count: draftCount, tone: packageStageClass("DRAFT") },
    {
      key: "READY_FOR_HANDOFF",
      label: t("opsExportPackages.readyForHandoff"),
      count: readyCount,
      tone: packageStageClass("READY_FOR_HANDOFF"),
    },
    {
      key: "HANDOFF_CREATED",
      label: t("opsExportPackages.handoffCreated"),
      count: handedOffCount,
      tone: packageStageClass("HANDOFF_CREATED"),
    },
    {
      key: "FAILED_NEEDS_ATTENTION",
      label: t("opsExportPackages.needsAttention"),
      count: attentionCount,
      tone:
        attentionCount > 0
          ? `${packageStageClass("FAILED_NEEDS_ATTENTION")} is-warning`
          : packageStageClass("FAILED_NEEDS_ATTENTION"),
    },
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
      key: "draft",
      label: t("opsExportPackages.draftPackages"),
      detail: t("opsExportPackages.draftPackagesDetail"),
      count: draftCount,
      tone: packageStageClass("DRAFT"),
      filter: "DRAFT",
    },
    {
      key: "linked",
      label: t("opsExportPackages.linkedHandoffs"),
      detail: t("opsExportPackages.linkedHandoffsDetail"),
      count: linkedHandoffCount,
      tone: packageStageClass("HANDOFF_CREATED"),
    },
    {
      key: "avg",
      label: t("opsExportPackages.avgItemsPacked"),
      detail: t("opsExportPackages.avgItemsPackedDetail"),
      count: avgItemsPacked,
      tone: "is-avg",
    },
    {
      key: "items",
      label: t("opsExportPackages.itemsPacked"),
      detail: t("opsExportPackages.itemsPackedDetail"),
      count: itemsPackedCount,
      tone: "is-items",
    },
  ];

  const mixDenom = Math.max(packages.length, 1);
  const draftDeg = (draftCount / mixDenom) * 360;
  const readyDeg = (readyCount / mixDenom) * 360;
  const handedDeg = (handedOffCount / mixDenom) * 360;
  const attentionDeg = (attentionCount / mixDenom) * 360;
  const donutGradient =
    packages.length === 0
      ? "conic-gradient(#d5e0db 0deg 90deg, #c5d4ce 90deg 180deg, #b7c7c0 180deg 270deg, #a9bab3 270deg 360deg)"
      : `conic-gradient(#8aa39a 0deg ${draftDeg}deg, #2f8f6f ${draftDeg}deg ${draftDeg + readyDeg}deg, #4f6fbf ${draftDeg + readyDeg}deg ${draftDeg + readyDeg + handedDeg}deg, #c4841a ${draftDeg + readyDeg + handedDeg}deg ${draftDeg + readyDeg + handedDeg + attentionDeg}deg, #d5e0db ${draftDeg + readyDeg + handedDeg + attentionDeg}deg 360deg)`;

  const refreshAction = (
    <TopbarRefreshButton busy={request.refreshing} disabled={request.initialLoading} onClick={() => void load()} />
  );

  const shellProps = {
    actions: refreshAction,
    description: t("opsExportPackages.description"),
    title: t("opsExportPackages.title"),
  } as const;

  const status = !loadedAt && !request.error ? "loading" : request.error && !loadedAt ? "error" : "success";
  const skeleton = <IntelligenceTableSkeleton label={t("opsExportPackages.loadingDetail")} rows={7} />;

  const rail = (
    <header className="export-packages-rail">
      <div className="export-packages-rail__copy">
        <strong>{t("opsExportPackages.packageRecords")}</strong>
        {loadedAt ? (
          <em>
            {t("opsExportPackages.loadedAt")}
            {" · "}
            <time dateTime={loadedAt}>{formatRailLoadedAt(loadedAt)}</time>
          </em>
        ) : null}
      </div>
      <nav className="export-packages-rail__links" aria-label={t("opsExportPackages.triage")}>
        <Link className="export-packages-rail__link" href="/selection/reup-queue">
          <ExportDockIcon kind="queue" />
          <span>{t("opsExportPackages.openReupQueue")}</span>
        </Link>
        <Link className="export-packages-rail__link" href="/publishing/publish-handoffs">
          <ExportDockIcon kind="handoff" />
          <span>{t("opsExportPackages.openHandoffs")}</span>
        </Link>
      </nav>
    </header>
  );

  const mixPanel =
    status === "success" ? (
      <aside aria-label={t("opsExportPackages.stageFilter")} className="export-packages-mix">
        <div className="export-packages-mix__board">
          <div className="export-packages-mix__stage" role="tablist">
            <button
              aria-label={t("opsExportPackages.filterAll")}
              aria-selected={stageFilter === "all"}
              className={`export-packages-mix__donut${packages.length === 0 ? " is-empty" : ""}${
                stageFilter === "all" ? " is-current" : ""
              }`.trim()}
              onClick={() => setStageFilter("all")}
              role="tab"
              style={{ background: donutGradient }}
              type="button"
            >
              <span className="export-packages-mix__donut-core">
                <b>{packages.length}</b>
                <small>{t("opsExportPackages.filterAll")}</small>
              </span>
            </button>
            <ul className="export-packages-mix__legend">
              {mixSlices.map((slice) => {
                const pct = Math.round((slice.count / mixDenom) * 100);
                return (
                  <li key={slice.key}>
                    <button
                      aria-selected={stageFilter === slice.key}
                      className={`export-packages-mix__legend-item ${slice.tone}${slice.count === 0 ? " is-empty" : ""}${
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
          <div aria-label={t("opsExportPackages.spectrumSignals")} className="export-packages-mix__signals">
            {mixSignals.map((signal) => {
              const active = signal.filter != null && stageFilter === signal.filter;
              const className = `export-packages-mix__signal ${signal.tone}${signal.count === 0 ? " is-empty" : ""}${
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
      <aside aria-hidden="true" className={`export-packages-mix is-${status}`}>
        <div className="export-packages-mix__board">
          <div className="export-packages-mix__stage">
            <div className="export-packages-mix__donut is-placeholder">
              <span className="export-packages-mix__donut-core">
                <b>—</b>
                <small>{t("opsExportPackages.filterAll")}</small>
              </span>
            </div>
            <ul className="export-packages-mix__legend is-placeholder">
              {mixSlices.map((slice) => (
                <li key={slice.key}>
                  <span className={`export-packages-mix__legend-item ${slice.tone} is-empty`}>
                    <i aria-hidden="true" />
                    <span>{slice.label}</span>
                    <em>—</em>
                    <b>—</b>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="export-packages-mix__signals is-placeholder">
            {mixSignals.map((signal) => (
              <div className={`export-packages-mix__signal ${signal.tone} is-empty`} key={signal.key}>
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
          <section aria-label={t("opsExportPackages.attention")} className="export-packages-attention">
            <strong>{t("opsExportPackages.attention")}</strong>
            <span>{needsAttention.length}</span>
            <p>{t("opsExportPackages.needsAttentionDetail")}</p>
            <button className="export-packages-attention__jump" onClick={() => setStageFilter("FAILED_NEEDS_ATTENTION")} type="button">
              {t("opsExportPackages.filterAttention")}
            </button>
          </section>
        ) : null}
        {packages.length === 0 ? (
          <div className="export-packages-empty">
            <strong>{t("opsExportPackages.empty")}</strong>
          </div>
        ) : visiblePackages.length === 0 ? (
          <div className="export-packages-empty">
            <strong>{t("opsExportPackages.filterEmpty")}</strong>
          </div>
        ) : (
          <ul className="export-packages-manifest">
            {visiblePackages.map((item) => (
              <ManifestSlip item={item} key={item.id} t={t} />
            ))}
          </ul>
        )}
        <p className="export-packages-footnote">{t("opsExportPackages.noAutoPublish")}</p>
      </>
    ) : (
      <span />
    );

  return (
    <OperatorStudioShell {...shellProps}>
      <main className="export-packages-page is-v4">
        <div className="export-packages-bay">
          {rail}
          <div className="export-packages-bay__body">
            {mixPanel}
            <section aria-label={t("opsExportPackages.packages")} className="export-packages-dock">
              <AsyncContentBoundary
                errorState={
                  <OpsState title={t("opsExportPackages.unavailableTitle")} detail={request.error?.message ?? t("opsExportPackages.loadError")} retry={() => void load()} />
                }
                loadingLabel={t("opsExportPackages.loadingDetail")}
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

function packageStageClass(status: string): string {
  if (status === "FAILED_NEEDS_ATTENTION") return "is-attention";
  if (status === "HANDOFF_CREATED") return "is-handed";
  if (status === "READY_FOR_HANDOFF") return "is-ready";
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
    minute: "2-digit",
  });
}

function ExportDockIcon({ kind }: { kind: "queue" | "handoff" }) {
  if (kind === "queue") {
    return (
      <svg aria-hidden="true" className="export-packages-rail__link-icon" fill="none" viewBox="0 0 20 20">
        <path d="M4.5 6.2h11M4.5 10h11M4.5 13.8h7.2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="export-packages-rail__link-icon" fill="none" viewBox="0 0 20 20">
      <path
        d="M5.2 5.2h6.2a1.4 1.4 0 0 1 1.4 1.4v7.8a1.4 1.4 0 0 1-1.4 1.4H5.2a1.4 1.4 0 0 1-1.4-1.4V6.6a1.4 1.4 0 0 1 1.4-1.4Z"
        stroke="currentColor"
        strokeWidth="1.55"
      />
      <path d="M7.1 8.4h3.8M7.1 11h2.6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.55" />
      <path
        d="M12.2 7.2h1.7a1.9 1.9 0 0 1 1.9 1.9v1.1l1.4-.9v3.4l-1.4-.9v1.1a1.9 1.9 0 0 1-1.9 1.9h-1.7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.55"
      />
    </svg>
  );
}

function ManifestSlip({ item, t }: { item: ExportPackage; t: (key: string) => string }) {
  const stage = packageStageClass(item.status);
  const title = item.label || `${t("opsExportPackages.package")} ${item.id.slice(0, 8)}`;
  const handoffCount = item.publish_handoff_ids.length;
  const seals = Math.min(Math.max(item.item_count, 0), 8);
  return (
    <li>
      <Link
        aria-label={`${t("opsExportPackages.open")}: ${title}`}
        className={`export-packages-manifest__slip ${stage}`.trim()}
        href={`/publishing/export-packages/${item.id}`}
      >
        <span aria-hidden="true" className="export-packages-manifest__stamp" />
        <div className="export-packages-manifest__identity">
          <strong className="export-packages-manifest__title" title={item.id}>
            {title}
          </strong>
          <p className="export-packages-manifest__meta">
            <span>
              {item.item_count} {t("opsExportPackages.items")}
            </span>
            <span aria-hidden="true">·</span>
            <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
          </p>
        </div>
        <div className="export-packages-manifest__seals" aria-hidden="true">
          {Array.from({ length: seals }, (_, index) => (
            <i key={index} />
          ))}
          {item.item_count > seals ? <em>+{item.item_count - seals}</em> : null}
        </div>
        <div className="export-packages-manifest__signal">
          <span className={`export-packages-chip ${stage}`}>{humanizeStatus(item.status)}</span>
          <span className={`export-packages-chip tone-${handoffCount > 0 ? "good" : "muted"}`}>
            {handoffCount} {handoffCount === 1 ? t("opsExportPackages.handoff") : t("opsExportPackages.handoffs")}
          </span>
          <span aria-hidden="true" className="export-packages-manifest__open">
            <svg className="export-packages-manifest__open-icon" fill="none" viewBox="0 0 20 20">
              <path d="m7.5 4.5 5 5.5-5 5.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
            </svg>
          </span>
        </div>
      </Link>
    </li>
  );
}
