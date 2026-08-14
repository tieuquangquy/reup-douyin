"use client";

import { useEffect, useState } from "react";
import { fetchAffiliateOpportunityQueue, runPublicationGrowthScore } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { AffiliateOpportunityItem, AffiliateOpportunityQueueResponse } from "../../types/growth-intelligence";
import { formatDateTime } from "../ops-console/OpsShared";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { WorkItemDetailsDrawer } from "../shared/WorkItemDetailsDrawer";
import { AffiliateCommentPlacementPanel } from "./AffiliateCommentPlacementPanel";
import { IntelligenceSpectrumSkeleton, IntelligenceTableSkeleton } from "./IntelligenceDataSkeleton";

const EMPTY_QUEUE: AffiliateOpportunityQueueResponse = {
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
  kpis: {
    eligible_count: 0,
    priority_count: 0,
    monitor_count: 0,
    do_not_place_count: 0,
    insufficient_data_count: 0,
    stale_count: 0,
  },
};

function scoreClass(value: number | null) {
  if (value == null) return "is-empty";
  if (value >= 70) return "is-high";
  if (value >= 40) return "is-medium";
  return "is-low";
}

function scoreMax(key: string) {
  if (key === "view_velocity") return 35;
  if (key === "view_acceleration") return 25;
  if (key === "engagement_quality") return 20;
  return 10;
}

function OpportunityToolbarGlyph({ kind }: { kind: "search" | "refresh" | "spark" | "open" | "shield" }) {
  if (kind === "search") {
    return (
      <svg aria-hidden="true" className="opportunity-ranking-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="6.25" stroke="currentColor" strokeWidth="1.85" />
        <path d="m16.1 16.1 4.1 4.1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "spark") {
    return (
      <svg aria-hidden="true" className="opportunity-ranking-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M12 4.2 13 8.8 17.5 9.8 13 10.8 12 15.4 11 10.8 6.5 9.8 11 8.8Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "open") {
    return (
      <svg aria-hidden="true" className="opportunity-ranking-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M14 5h5v5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
        <path d="M10 14 19 5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.85" />
        <path d="M19 13.5V19H5V5h5.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "shield") {
    return (
      <svg aria-hidden="true" className="opportunity-ranking-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M12 3.6 19 6.2v5.1c0 4.4-2.9 7.5-7 8.9-4.1-1.4-7-4.5-7-8.9V6.2L12 3.6Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
        <path d="m9.4 12.1 1.8 1.8 3.6-3.7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="opportunity-ranking-toolbar__glyph" fill="none" viewBox="0 0 24 24">
      <path d="M19.2 8.2V12h-3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M4.8 15.8V12h3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M7.05 9.15a6.2 6.2 0 0 1 10.4-1.75L19.2 9.15M4.8 14.85l1.75 1.75a6.2 6.2 0 0 0 10.4-1.75" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
    </svg>
  );
}

export function AffiliateOpportunityRanking() {
  const t = useT();
  const { notify } = useNotice();
  const [queue, setQueue] = useState<AffiliateOpportunityQueueResponse>(EMPTY_QUEUE);
  const [recommendation, setRecommendation] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchAffiliateOpportunityQueue({
        recommendation: recommendation || undefined,
        query: query || undefined,
        limit: 100,
      });
      setQueue(payload);
      setHasLoadedOnce(true);
      setError(null);
      if (showNotice) notify({ message: t("opportunityRanking.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opportunityRanking.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 15_000);
    return () => clearInterval(timer);
  }, [recommendation, query]);

  function openItem(item: AffiliateOpportunityItem) {
    if (!item.growth_assessment) return;
    setExpandedId((value) => (value === item.platform_publication_id ? null : item.platform_publication_id));
  }

  async function calculate(item: AffiliateOpportunityItem) {
    setBusyId(item.platform_publication_id);
    setError(null);
    try {
      const result = await runPublicationGrowthScore(item.platform_publication_id);
      notify({
        message: result.growth_assessment
          ? t("opportunityRanking.scoreCurrent")
          : t("opportunityRanking.queued").replace("{id}", result.job?.id.slice(0, 8) ?? "—"),
        tone: result.growth_assessment ? "info" : "success",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("opportunityRanking.runError"));
    } finally {
      setBusyId(null);
    }
  }

  const coldLoading = loading && !hasLoadedOnce;
  const kpis = queue.kpis;
  const statusTotal = Math.max(
    kpis.priority_count + kpis.monitor_count + kpis.do_not_place_count + kpis.insufficient_data_count,
    kpis.eligible_count,
    1,
  );
  const priorityDeg = (kpis.priority_count / statusTotal) * 360;
  const monitorDeg = (kpis.monitor_count / statusTotal) * 360;
  const blockedDeg = (kpis.do_not_place_count / statusTotal) * 360;
  const insufficientDeg = (kpis.insufficient_data_count / statusTotal) * 360;
  const donutGradient =
    kpis.eligible_count === 0
      ? "conic-gradient(#d5e0db 0deg 90deg, #c5d4ce 90deg 180deg, #b7c7c0 180deg 270deg, #a9bab3 270deg 360deg)"
      : `conic-gradient(#2f8f6f 0deg ${priorityDeg}deg, #c4841a ${priorityDeg}deg ${priorityDeg + monitorDeg}deg, #ac4337 ${priorityDeg + monitorDeg}deg ${priorityDeg + monitorDeg + blockedDeg}deg, #6f857c ${priorityDeg + monitorDeg + blockedDeg}deg ${priorityDeg + monitorDeg + blockedDeg + insufficientDeg}deg, #d5e0db ${priorityDeg + monitorDeg + blockedDeg + insufficientDeg}deg 360deg)`;
  const barScale = Math.max(kpis.eligible_count, 1);
  const statusLegend = [
    {
      key: "priority" as const,
      label: t("opportunityRanking.priority"),
      count: kpis.priority_count,
      pct: Math.round((kpis.priority_count / statusTotal) * 100),
    },
    {
      key: "monitor" as const,
      label: t("opportunityRanking.monitor"),
      count: kpis.monitor_count,
      pct: Math.round((kpis.monitor_count / statusTotal) * 100),
    },
    {
      key: "blocked" as const,
      label: t("opportunityRanking.doNotPlace"),
      count: kpis.do_not_place_count,
      pct: Math.round((kpis.do_not_place_count / statusTotal) * 100),
    },
    {
      key: "insufficient" as const,
      label: t("opportunityRanking.insufficient"),
      count: kpis.insufficient_data_count,
      pct: Math.round((kpis.insufficient_data_count / statusTotal) * 100),
    },
  ];
  const signalBars = [
    { key: "priority" as const, label: t("opportunityRanking.priority"), count: kpis.priority_count, filter: "PRIORITY" },
    { key: "monitor" as const, label: t("opportunityRanking.monitor"), count: kpis.monitor_count, filter: "MONITOR" },
    { key: "blocked" as const, label: t("opportunityRanking.doNotPlace"), count: kpis.do_not_place_count, filter: "DO_NOT_PLACE" },
    {
      key: "insufficient" as const,
      label: t("opportunityRanking.insufficient"),
      count: kpis.insufficient_data_count,
      filter: "INSUFFICIENT_DATA",
    },
  ];
  const activeItem = queue.items.find((item) => item.platform_publication_id === expandedId) ?? null;
  const activeGrowth = activeItem?.growth_assessment ?? null;

  return (
    <section className="opportunity-ranking-page is-v1">
      {error ? (
        <div className="inline-error" role="alert">
          {error}
        </div>
      ) : null}

      {coldLoading ? (
        <IntelligenceSpectrumSkeleton className="opportunity-ranking-spectrum" label={t("opportunityRanking.loading")} />
      ) : (
        <section aria-label={t("opportunityRanking.spectrumStatusMix")} className="opportunity-ranking-spectrum">
          <div className="opportunity-ranking-spectrum__stage">
            <header className="opportunity-ranking-spectrum__head">
              <span className="opportunity-ranking-spectrum__eyebrow">{t("opportunityRanking.spectrumStatusMix")}</span>
              <small className="opportunity-ranking-spectrum__hint">{t("opportunityRanking.eligibleHint")}</small>
            </header>

            <div className="opportunity-ranking-spectrum__status">
              <div aria-hidden="true" className="opportunity-ranking-spectrum__donut" style={{ background: donutGradient }}>
                <div className="opportunity-ranking-spectrum__donut-core">
                  <b>{kpis.eligible_count}</b>
                  <small>{t("opportunityRanking.eligible")}</small>
                </div>
              </div>
              <ul className="opportunity-ranking-spectrum__legend" aria-label={t("opportunityRanking.recommendation")}>
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

            <div className="opportunity-ranking-spectrum__attention">
              <span className="opportunity-ranking-spectrum__attention-label">{t("opportunityRanking.spectrumAttention")}</span>
              <div className="opportunity-ranking-spectrum__plot" role="list">
                {signalBars.map((bar) => {
                  const barW = bar.count === 0 ? 0 : Math.max(8, Math.round((bar.count / barScale) * 100));
                  const active = recommendation === bar.filter;
                  return (
                    <button
                      aria-label={`${bar.label}: ${bar.count}`}
                      aria-pressed={active}
                      className={`is-${bar.key}${bar.count === 0 ? " is-empty" : ""}${active ? " is-current" : ""}`}
                      key={bar.key}
                      role="listitem"
                      style={{ ["--bar-w" as string]: `${barW}%` }}
                      type="button"
                      onClick={() => setRecommendation(active ? "" : bar.filter)}
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

      <section aria-label={t("opportunityRanking.title")} className="opportunity-ranking-toolbar is-v1">
        <select
          aria-label={t("opportunityRanking.recommendation")}
          value={recommendation}
          onChange={(event) => setRecommendation(event.target.value)}
        >
          <option value="">{t("opportunityRanking.allRecommendations")}</option>
          <option value="PRIORITY">{t("opportunityRanking.priority")}</option>
          <option value="MONITOR">{t("opportunityRanking.monitor")}</option>
          <option value="DO_NOT_PLACE">{t("opportunityRanking.doNotPlace")}</option>
          <option value="INSUFFICIENT_DATA">{t("opportunityRanking.insufficient")}</option>
        </select>
        <form
          className="opportunity-ranking-toolbar__search"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(queryInput.trim());
          }}
        >
          <input
            aria-label={t("opportunityRanking.search")}
            placeholder={t("opportunityRanking.searchPlaceholder")}
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
          />
          <AsyncButton
            aria-label={t("opportunityRanking.apply")}
            className="opportunity-ranking-toolbar__icon-btn"
            leadingIcon={<OpportunityToolbarGlyph kind="search" />}
            pending={loading}
            pendingLabel={<span className="visually-hidden">{t("opportunityRanking.apply")}</span>}
            title={t("opportunityRanking.apply")}
            type="submit"
          >
            <span className="visually-hidden">{t("opportunityRanking.apply")}</span>
          </AsyncButton>
        </form>
        <button
          aria-label={t("opportunityRanking.noAutoPlacement")}
          className="opportunity-ranking-toolbar__safety"
          title={`${t("opportunityRanking.separateScores")} ${t("opportunityRanking.noCombinedScore")}`}
          type="button"
        >
          <OpportunityToolbarGlyph kind="shield" />
          <span className="visually-hidden">{t("opportunityRanking.noAutoPlacement")}</span>
        </button>
        <AsyncButton
          aria-label={t("common.refresh")}
          className="opportunity-ranking-toolbar__icon-btn"
          leadingIcon={<OpportunityToolbarGlyph kind="refresh" />}
          pending={loading}
          pendingLabel={<span className="visually-hidden">{t("common.refresh")}</span>}
          title={t("common.refresh")}
          onClick={() => void load(true)}
        >
          <span className="visually-hidden">{t("common.refresh")}</span>
        </AsyncButton>
      </section>

      <section className="opportunity-ranking-table-wrap is-v1">
        <header className="opportunity-ranking-results-head">
          <div>
            <strong>{t("opportunityRanking.results").replace("{count}", String(queue.total))}</strong>
            <small title={t("opportunityRanking.separateScores")}>{t("opportunityRanking.noCombinedScore")}</small>
          </div>
          {kpis.stale_count > 0 ? (
            <span className="opportunity-ranking-results-head__stale">
              {t("opportunityRanking.stale")} · {kpis.stale_count}
            </span>
          ) : null}
        </header>

        {coldLoading ? (
          <IntelligenceTableSkeleton className="opportunity-ranking-loading" label={t("opportunityRanking.loading")} />
        ) : queue.items.length === 0 ? (
          <div className="opportunity-ranking-empty">
            <strong>{t("opportunityRanking.empty")}</strong>
            <small>{t("opportunityRanking.emptyHint")}</small>
          </div>
        ) : (
          <table className="opportunity-ranking-table is-v1">
            <thead>
              <tr>
                <th>{t("opportunityRanking.reel")}</th>
                <th>{t("opportunityRanking.product")}</th>
                <th>{t("opportunityRanking.growthScore")}</th>
                <th>{t("opportunityRanking.affiliateFit")}</th>
                <th>{t("opportunityRanking.recommendation")}</th>
                <th>{t("opportunityRanking.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {queue.items.map((item) => {
                const growth = item.growth_assessment;
                const jobActive = Boolean(item.latest_job && ["QUEUED", "RUNNING", "RETRYABLE"].includes(item.latest_job.status));
                const open = expandedId === item.platform_publication_id;
                const runLabel = growth ? t("opportunityRanking.recalculate") : t("opportunityRanking.calculate");
                const detailLabel =
                  item.recommendation === "PRIORITY" ? t("affiliateComment.prepare") : t("opportunityRanking.breakdown");

                return (
                  <tr
                    className={[open ? "is-open" : "", growth ? "is-clickable" : ""].filter(Boolean).join(" ") || undefined}
                    key={item.platform_publication_id}
                    onClick={growth ? () => openItem(item) : undefined}
                  >
                    <td>
                      <div className="opportunity-ranking-reel">
                        {item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span>Reel</span>}
                        <div>
                          <strong>{item.caption || item.external_reel_id || "Reel"}</strong>
                          <small>{item.page_display_name}</small>
                          <small>{item.published_at ? formatDateTime(item.published_at) : item.external_reel_id}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="opportunity-ranking-product">
                        <strong>{item.selected_product_name}</strong>
                        <small>
                          {item.selected_product_platform} · {item.product_match_decision}
                        </small>
                        <span className={`is-${item.selected_product_availability.toLowerCase()}`}>
                          {item.selected_product_availability}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="opportunity-score-cell">
                        <b className={scoreClass(growth?.growth_score ?? null)}>
                          {growth?.growth_score == null ? "—" : Math.round(growth.growth_score)}
                        </b>
                        <small>
                          {growth
                            ? `${t(`opportunityRanking.confidenceValue.${growth.confidence}`)} · ${t(`opportunityRanking.growthStatus.${growth.status}`)}`
                            : t("opportunityRanking.notScored")}
                        </small>
                        {item.growth_is_stale ? <em>{t("opportunityRanking.stale")}</em> : null}
                      </div>
                    </td>
                    <td>
                      <b className={`opportunity-fit-score ${scoreClass(item.affiliate_fit_score)}`}>
                        {item.affiliate_fit_score == null ? "—" : Math.round(item.affiliate_fit_score)}
                      </b>
                    </td>
                    <td>
                      <div className="opportunity-recommendation-cell">
                        <span className={`is-${item.recommendation.toLowerCase()}`}>
                          {t(`opportunityRanking.recommendationValue.${item.recommendation}`)}
                        </span>
                        <small>{t(`opportunityRanking.reason.${item.recommendation_reason}`)}</small>
                      </div>
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className="opportunity-ranking-actions">
                        <AsyncButton
                          aria-label={runLabel}
                          className="opportunity-ranking-actions__icon-btn is-run"
                          disabled={jobActive}
                          leadingIcon={<OpportunityToolbarGlyph kind={growth ? "refresh" : "spark"} />}
                          pending={busyId === item.platform_publication_id}
                          pendingLabel={<span className="visually-hidden">{runLabel}</span>}
                          title={runLabel}
                          onClick={() => void calculate(item)}
                        >
                          <span className="visually-hidden">{runLabel}</span>
                        </AsyncButton>
                        {growth ? (
                          <button
                            aria-expanded={open}
                            aria-haspopup="dialog"
                            aria-label={open ? t("opportunityRanking.close") : detailLabel}
                            className={`opportunity-ranking-actions__icon-btn is-detail${open ? " is-open" : ""}`}
                            title={open ? t("opportunityRanking.close") : detailLabel}
                            type="button"
                            onClick={() => openItem(item)}
                          >
                            <OpportunityToolbarGlyph kind="open" />
                          </button>
                        ) : null}
                        <a
                          aria-label={t("opportunityRanking.openPublication")}
                          className="opportunity-ranking-actions__icon-btn is-link"
                          href={`/publishing/publications?account_id=${item.platform_account_id}`}
                          title={t("opportunityRanking.openPublication")}
                        >
                          <OpportunityToolbarGlyph kind="open" />
                          <span className="visually-hidden">{t("opportunityRanking.openPublication")}</span>
                        </a>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <WorkItemDetailsDrawer
        eyebrow={t("opportunityRanking.breakdown")}
        headerExtra={
          activeItem && activeGrowth ? (
            <div className="opportunity-ranking-detail__header-extra">
              <span className="opportunity-ranking-detail__version">
                {activeGrowth.score_version} · {activeGrowth.snapshot_count} {t("opportunityRanking.snapshots")}
              </span>
              <p className="opportunity-ranking-detail__context">
                <strong>{activeItem.caption || activeItem.external_reel_id || "Reel"}</strong>
                <span>{activeItem.selected_product_name}</span>
              </p>
            </div>
          ) : null
        }
        open={Boolean(activeItem && activeGrowth)}
        title={t("opportunityRanking.breakdownTitle")}
        titleId="opportunity-ranking-detail-title"
        onClose={() => setExpandedId(null)}
      >
        {activeItem && activeGrowth ? (
          <section className="opportunity-ranking-detail is-v1">
            <p className="opportunity-ranking-detail__safety">{t("opportunityRanking.noCombinedScore")}</p>
            <div className="opportunity-ranking-detail__scores">
              {Object.entries(activeGrowth.score_breakdown).map(([key, value]) => (
                <article key={key}>
                  <span>{t(`opportunityRanking.score.${key}`)}</span>
                  <b>{Math.round(value)}</b>
                  <small>/ {scoreMax(key)}</small>
                </article>
              ))}
            </div>
            {activeGrowth.evidence.length ? (
              <ul className="opportunity-ranking-detail__evidence">
                {activeGrowth.evidence.map((entry) => (
                  <li key={entry}>{entry.replaceAll("_", " ")}</li>
                ))}
              </ul>
            ) : null}
            <AffiliateCommentPlacementPanel item={activeItem} />
          </section>
        ) : null}
      </WorkItemDetailsDrawer>
    </section>
  );
}
