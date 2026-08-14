"use client";

import { useEffect, useState } from "react";
import { fetchContentClassificationQueue, runPublicationContentClassification } from "../../lib/api";
import { useT } from "../../lib/i18n";
import { classificationSourceTitle, getClassificationSourcePresentation } from "../../lib/contentClassificationPresentation";
import type { ContentClassificationQueueItem, ContentClassificationQueueResponse } from "../../types/content-intelligence";
import type { PlatformAccount } from "../../types/publish-draft";
import { formatDateTime } from "../ops-console/OpsShared";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { IntelligenceSpectrumSkeleton, IntelligenceTableSkeleton } from "./IntelligenceDataSkeleton";

function ClassificationToolbarGlyph({ kind }: { kind: "search" | "refresh" | "spark" | "open" }) {
  if (kind === "search") {
    return (
      <svg aria-hidden="true" className="classification-queue-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
        <path d="m16.2 16.2 4.3 4.3" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
      </svg>
    );
  }
  if (kind === "spark") {
    return (
      <svg aria-hidden="true" className="classification-queue-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M12 3.5 13.1 8.8 18.5 10 13.1 11.2 12 16.5 10.9 11.2 5.5 10 10.9 8.8z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
      </svg>
    );
  }
  if (kind === "open") {
    return (
      <svg aria-hidden="true" className="classification-queue-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M14 4h6v6M20 4l-9 9" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
        <path d="M18 13v7H4V6h7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="classification-queue-toolbar__glyph" fill="none" viewBox="0 0 24 24">
      <path d="M20 7v5h-5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M4 17v-5h5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M6.1 9a7 7 0 0 1 11.8-2L20 9M4 15l2.1 2a7 7 0 0 0 11.8-2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </svg>
  );
}

function ClassificationResultsHeadGlyph({ kind }: { kind: "unclassified" | "review" | "approved" | "low" }) {
  if (kind === "unclassified") {
    return (
      <svg aria-hidden="true" className="classification-queue-results-head__glyph" fill="none" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeDasharray="2.6 2.4" strokeWidth="1.8" />
        <path d="M12 9.2v3.2M12 15.4h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
      </svg>
    );
  }
  if (kind === "review") {
    return (
      <svg aria-hidden="true" className="classification-queue-results-head__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M3.8 12s3.2-5.2 8.2-5.2S20.2 12 20.2 12s-3.2 5.2-8.2 5.2S3.8 12 3.8 12Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
        <circle cx="12" cy="12" r="2.35" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    );
  }
  if (kind === "approved") {
    return (
      <svg aria-hidden="true" className="classification-queue-results-head__glyph" fill="none" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="7.25" stroke="currentColor" strokeWidth="1.8" />
        <path d="m8.6 12.2 2.2 2.2 4.6-4.7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.9" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="classification-queue-results-head__glyph" fill="none" viewBox="0 0 24 24">
      <path d="M12 4.4 20.1 18.6H3.9L12 4.4Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.8" />
      <path d="M12 10.2v3.4M12 16.4h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.9" />
    </svg>
  );
}

const EMPTY_QUEUE: ContentClassificationQueueResponse = {
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
  kpis: {
    total_publications: 0,
    unclassified_count: 0,
    needs_review_count: 0,
    approved_count: 0,
    overridden_count: 0,
    low_confidence_count: 0,
  },
};


export function ContentClassificationQueue({
  accounts,
  onOpenPublication,
}: {
  accounts: PlatformAccount[];
  onOpenPublication: (item: ContentClassificationQueueItem) => Promise<void>;
}) {
  const t = useT();
  const { notify } = useNotice();
  const [queue, setQueue] = useState(EMPTY_QUEUE);
  const [accountFilter, setAccountFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [lowConfidenceOnly, setLowConfidenceOnly] = useState(false);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchContentClassificationQueue({
        platformAccountId: accountFilter || undefined,
        decisionStatus: statusFilter || undefined,
        lowConfidenceOnly,
        query: query || undefined,
        limit: 100,
      });
      setQueue(payload);
      setHasLoadedOnce(true);
      setError(null);
      if (showNotice) notify({ message: t("classificationQueue.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("classificationQueue.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 15_000);
    return () => clearInterval(timer);
  }, [accountFilter, statusFilter, lowConfidenceOnly, query]);

  async function classify(item: ContentClassificationQueueItem) {
    setBusy(item.platform_publication_id);
    setError(null);
    try {
      const result = await runPublicationContentClassification(item.platform_publication_id);
      notify({
        message: result.classification
          ? t("classificationQueue.alreadyCurrent")
          : t("classificationQueue.queued").replace("{id}", result.job?.id.slice(0, 8) ?? "—"),
        tone: result.classification ? "info" : "success",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("classificationQueue.runError"));
    } finally {
      setBusy(null);
    }
  }

  const kpis = queue.kpis;
  const statusTotal = Math.max(
    kpis.unclassified_count + kpis.needs_review_count + kpis.approved_count + kpis.overridden_count,
    kpis.total_publications,
    1,
  );
  const unclassifiedDeg = (kpis.unclassified_count / statusTotal) * 360;
  const reviewDeg = (kpis.needs_review_count / statusTotal) * 360;
  const approvedDeg = (kpis.approved_count / statusTotal) * 360;
  const donutGradient = kpis.total_publications === 0
    ? "conic-gradient(#d5e0db 0deg 90deg, #c5d4ce 90deg 180deg, #b7c7c0 180deg 270deg, #a9bab3 270deg 360deg)"
    : `conic-gradient(#6f857c 0deg ${unclassifiedDeg}deg, #c4841a ${unclassifiedDeg}deg ${unclassifiedDeg + reviewDeg}deg, #2f8f6f ${unclassifiedDeg + reviewDeg}deg ${unclassifiedDeg + reviewDeg + approvedDeg}deg, #6b7bb8 ${unclassifiedDeg + reviewDeg + approvedDeg}deg 360deg)`;
  const barScale = Math.max(kpis.total_publications, 1);
  const statusLegend = [
    {
      key: "unclassified" as const,
      label: t("classificationQueue.statusValue.UNCLASSIFIED"),
      count: kpis.unclassified_count,
      pct: Math.round((kpis.unclassified_count / statusTotal) * 100),
    },
    {
      key: "review" as const,
      label: t("classificationQueue.statusValue.NEEDS_REVIEW"),
      count: kpis.needs_review_count,
      pct: Math.round((kpis.needs_review_count / statusTotal) * 100),
    },
    {
      key: "approved" as const,
      label: t("classificationQueue.statusValue.APPROVED"),
      count: kpis.approved_count,
      pct: Math.round((kpis.approved_count / statusTotal) * 100),
    },
    {
      key: "overridden" as const,
      label: t("classificationQueue.statusValue.OVERRIDDEN"),
      count: kpis.overridden_count,
      pct: Math.round((kpis.overridden_count / statusTotal) * 100),
    },
  ];
  const signalBars = [
    {
      key: "unclassified" as const,
      label: t("classificationQueue.unclassified"),
      count: kpis.unclassified_count,
      active: statusFilter === "UNCLASSIFIED" && !lowConfidenceOnly,
      onClick: () => {
        setLowConfidenceOnly(false);
        setStatusFilter(statusFilter === "UNCLASSIFIED" ? "" : "UNCLASSIFIED");
      },
    },
    {
      key: "review" as const,
      label: t("classificationQueue.needsReview"),
      count: kpis.needs_review_count,
      active: statusFilter === "NEEDS_REVIEW" && !lowConfidenceOnly,
      onClick: () => {
        setLowConfidenceOnly(false);
        setStatusFilter(statusFilter === "NEEDS_REVIEW" ? "" : "NEEDS_REVIEW");
      },
    },
    {
      key: "low" as const,
      label: t("classificationQueue.lowConfidence"),
      count: kpis.low_confidence_count,
      active: lowConfidenceOnly,
      onClick: () => {
        setStatusFilter("");
        setLowConfidenceOnly(!lowConfidenceOnly);
      },
    },
  ];
  const resultsHeadStats = [
    {
      key: "unclassified" as const,
      label: t("classificationQueue.statusValue.UNCLASSIFIED"),
      count: kpis.unclassified_count,
      active: statusFilter === "UNCLASSIFIED" && !lowConfidenceOnly,
      onClick: () => {
        setLowConfidenceOnly(false);
        setStatusFilter(statusFilter === "UNCLASSIFIED" ? "" : "UNCLASSIFIED");
      },
    },
    {
      key: "review" as const,
      label: t("classificationQueue.statusValue.NEEDS_REVIEW"),
      count: kpis.needs_review_count,
      active: statusFilter === "NEEDS_REVIEW" && !lowConfidenceOnly,
      onClick: () => {
        setLowConfidenceOnly(false);
        setStatusFilter(statusFilter === "NEEDS_REVIEW" ? "" : "NEEDS_REVIEW");
      },
    },
    {
      key: "approved" as const,
      label: t("classificationQueue.statusValue.APPROVED"),
      count: kpis.approved_count,
      active: statusFilter === "APPROVED" && !lowConfidenceOnly,
      onClick: () => {
        setLowConfidenceOnly(false);
        setStatusFilter(statusFilter === "APPROVED" ? "" : "APPROVED");
      },
    },
    {
      key: "low" as const,
      label: t("classificationQueue.lowConfidence"),
      count: kpis.low_confidence_count,
      active: lowConfidenceOnly,
      onClick: () => {
        setStatusFilter("");
        setLowConfidenceOnly(!lowConfidenceOnly);
      },
    },
  ];
  const coldLoading = loading && !hasLoadedOnce;

  return (
    <section className="classification-queue-page is-v10 is-v11 is-v12 is-v13 is-v14 is-v15 is-v16 is-v17 is-v18">
      {error ? <div className="inline-error" role="alert">{error}</div> : null}

      {coldLoading ? (
        <IntelligenceSpectrumSkeleton className="classification-queue-spectrum" label={t("classificationQueue.loading")} />
      ) : (
      <section aria-label={t("classificationQueue.title")} className="classification-queue-spectrum is-v11 is-v12 is-v13 is-v14 is-v15 is-v16 is-v17 is-v18">
        <div className="classification-queue-spectrum__stage">
          <header className="classification-queue-spectrum__head">
            <span className="classification-queue-spectrum__eyebrow">{t("classificationQueue.spectrumStatusMix")}</span>
            <small className="classification-queue-spectrum__hint">{t("classificationQueue.totalHint")}</small>
          </header>

          <div className="classification-queue-spectrum__status">
            <div aria-hidden="true" className="classification-queue-spectrum__donut" style={{ background: donutGradient }}>
              <div className="classification-queue-spectrum__donut-core">
                <b>{kpis.total_publications}</b>
                <small>{t("classificationQueue.total")}</small>
              </div>
            </div>
            <ul className="classification-queue-spectrum__legend" aria-label={t("classificationQueue.status")}>
              {statusLegend.map((slice) => (
                <li className={`is-${slice.key}`} key={slice.key} title={`${slice.pct}%`}>
                  <i aria-hidden="true" />
                  <span>{slice.label}</span>
                  <b>{slice.count}</b>
                  <em>{slice.pct}%</em>
                </li>
              ))}
            </ul>
          </div>

          <div className="classification-queue-spectrum__attention">
            <span className="classification-queue-spectrum__attention-label">{t("classificationQueue.spectrumAttention")}</span>
            <div className="classification-queue-spectrum__plot" role="list">
              {signalBars.map((bar) => {
                const barW = bar.count === 0 ? 0 : Math.max(8, Math.round((bar.count / barScale) * 100));
                return (
                  <button
                    aria-label={`${bar.label}: ${bar.count}`}
                    aria-pressed={bar.active}
                    className={`is-${bar.key}${bar.count === 0 ? " is-empty" : ""}${bar.active ? " is-current" : ""}`}
                    key={bar.key}
                    onClick={bar.onClick}
                    role="listitem"
                    style={{ ["--bar-w" as string]: `${barW}%` }}
                    type="button"
                  >
                    <span>{bar.label}</span>
                    <em aria-hidden="true" />
                    <strong>{bar.count}</strong>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>
      )}

      <section className="classification-queue-toolbar is-v19">
        <select
          aria-label={t("classificationQueue.page")}
          onChange={(event) => setAccountFilter(event.target.value)}
          value={accountFilter}
        >
          <option value="">{t("classificationQueue.allPages")}</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>{account.display_name}</option>
          ))}
        </select>
        <select
          aria-label={t("classificationQueue.status")}
          onChange={(event) => setStatusFilter(event.target.value)}
          value={statusFilter}
        >
          <option value="">{t("classificationQueue.allStatuses")}</option>
          {["UNCLASSIFIED", "NEEDS_REVIEW", "APPROVED", "OVERRIDDEN"].map((value) => (
            <option key={value} value={value}>{t(`classificationQueue.statusValue.${value}`)}</option>
          ))}
        </select>
        <label className="classification-queue-low-confidence">
          <input checked={lowConfidenceOnly} onChange={(event) => setLowConfidenceOnly(event.target.checked)} type="checkbox" />
          <span>{t("classificationQueue.onlyLowConfidence")}</span>
        </label>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(queryInput.trim());
          }}
        >
          <input
            aria-label={t("classificationQueue.search")}
            onChange={(event) => setQueryInput(event.target.value)}
            placeholder={t("classificationQueue.searchPlaceholder")}
            value={queryInput}
          />
          <AsyncButton
            aria-label={t("classificationQueue.apply")}
            className="classification-queue-toolbar__icon-btn is-apply"
            leadingIcon={<ClassificationToolbarGlyph kind="search" />}
            pending={loading}
            pendingLabel={t("classificationQueue.apply")}
            title={t("classificationQueue.apply")}
            type="submit"
          >
            <span className="visually-hidden">{t("classificationQueue.apply")}</span>
          </AsyncButton>
        </form>
        <AsyncButton
          aria-label={t("common.refresh")}
          className="classification-queue-toolbar__icon-btn is-refresh"
          leadingIcon={<ClassificationToolbarGlyph kind="refresh" />}
          pending={loading}
          pendingLabel={t("common.refresh")}
          title={t("common.refresh")}
          onClick={() => void load(true)}
        >
          <span className="visually-hidden">{t("common.refresh")}</span>
        </AsyncButton>
      </section>

      <section className="classification-queue-table-wrap is-v26 is-v27 is-v28 is-v29 is-v30 is-v31 is-v32 is-v33" aria-label={t("classificationQueue.title")}>
        <header className="classification-queue-results-head is-v33">
          <div className="classification-queue-results-head__title">
            <strong>{t("classificationQueue.title")}</strong>
            <small>{t("classificationQueue.results").replace("{count}", String(queue.total))}</small>
          </div>
          {!coldLoading ? (
            <div className="classification-queue-results-head__stats" role="group" aria-label={t("classificationQueue.status")}>
              {resultsHeadStats.map((stat) => (
                <button
                  aria-label={`${stat.label}: ${stat.count}`}
                  aria-pressed={stat.active}
                  className={`classification-queue-results-head__chip is-${stat.key}${stat.active ? " is-active" : ""}${stat.count === 0 ? " is-empty" : ""}`}
                  key={stat.key}
                  onClick={stat.onClick}
                  type="button"
                >
                  <ClassificationResultsHeadGlyph kind={stat.key} />
                  <span>{stat.label}</span>
                  <b>{stat.count}</b>
                </button>
              ))}
            </div>
          ) : null}
        </header>
        {coldLoading ? (
          <IntelligenceTableSkeleton className="classification-queue-loading" label={t("classificationQueue.loading")} />
        ) : queue.items.length === 0 ? (
          <p className="muted">{t("classificationQueue.empty")}</p>
        ) : (
          <table className="classification-queue-table is-v26 is-v27 is-v28 is-v29 is-v30 is-v31 is-v32 is-v33">
            <thead>
              <tr>
                <th>{t("classificationQueue.reel")}</th>
                <th>{t("classificationQueue.page")}</th>
                <th>{t("classificationQueue.result")}</th>
                <th>{t("contentClassification.confidence")}</th>
                <th>{t("classificationQueue.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {queue.items.map((item) => {
                const classification = item.classification;
                const status = classification?.decision_status ?? "UNCLASSIFIED";
                const source = classification ? getClassificationSourcePresentation(classification) : null;
                const jobActive = Boolean(item.latest_job && ["QUEUED", "RUNNING", "RETRYABLE"].includes(item.latest_job.status));
                const runLabel = classification ? t("contentClassification.reclassify") : t("contentClassification.run");
                const openLabel = classification ? t("classificationQueue.review") : t("classificationQueue.open");
                const statusTitle = [
                  t(`classificationQueue.statusValue.${status}`),
                  source ? classificationSourceTitle(source) : null,
                ].filter(Boolean).join(" · ");
                const jobTitle = item.latest_job
                  ? `${item.latest_job.status} · ${item.latest_job.progress_percent}%`
                  : "";
                return (
                  <tr key={item.platform_publication_id}>
                    <td>
                      <div className="classification-queue-reel">
                        {item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span>Reel</span>}
                        <div>
                          <b>{item.caption || item.external_reel_id || "Reel"}</b>
                          <small>{item.published_at ? formatDateTime(item.published_at) : item.external_reel_id}</small>
                        </div>
                      </div>
                    </td>
                    <td><span className="classification-queue-page-name">{item.page_display_name}</span></td>
                    <td>
                      <div className="classification-queue-result is-inline">
                        <span className={`classification-queue-status is-${status.toLowerCase()}`} title={statusTitle}>
                          {t(`classificationQueue.statusValue.${status}`)}
                        </span>
                        {classification?.primary_topic_name ? (
                          <span className="classification-queue-result__topic">{classification.primary_topic_name}</span>
                        ) : null}
                        {jobActive && item.latest_job ? (
                          <span className={`classification-queue-job is-chip is-${item.latest_job.status.toLowerCase()}`} title={jobTitle}>
                            <i />
                            <span className="classification-queue-job__short">{item.latest_job.progress_percent}%</span>
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td>
                      {classification ? (
                        <b className={`classification-confidence is-${classification.confidence >= 0.75 ? "high" : classification.confidence >= 0.5 ? "medium" : "low"}`}>
                          {Math.round(classification.confidence * 100)}%
                        </b>
                      ) : <span className="classification-queue-empty">—</span>}
                    </td>
                    <td>
                      <div className="classification-queue-actions">
                        <AsyncButton
                          aria-label={runLabel}
                          className={`classification-queue-table__icon-btn is-run${classification ? " is-rerun" : ""}`}
                          disabled={jobActive}
                          leadingIcon={<ClassificationToolbarGlyph kind={classification ? "refresh" : "spark"} />}
                          pending={busy === item.platform_publication_id}
                          pendingLabel={runLabel}
                          title={runLabel}
                          onClick={() => void classify(item)}
                        >
                          <span className="visually-hidden">{runLabel}</span>
                        </AsyncButton>
                        <button
                          aria-label={openLabel}
                          className="classification-queue-table__icon-btn is-open"
                          title={openLabel}
                          onClick={() => void onOpenPublication(item)}
                          type="button"
                        >
                          <ClassificationToolbarGlyph kind="open" />
                          <span className="visually-hidden">{openLabel}</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </section>
  );
}
