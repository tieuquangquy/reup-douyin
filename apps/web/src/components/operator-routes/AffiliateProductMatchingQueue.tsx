"use client";

import { useEffect, useState } from "react";
import { decideAffiliateProductMatch, fetchAffiliateProductMatchQueue, fetchAffiliateProducts, runAffiliateProductMatch } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { AffiliateProduct, AffiliateProductMatchQueueItem } from "../../types/affiliate";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { WorkItemDetailsDrawer } from "../shared/WorkItemDetailsDrawer";
import { formatDateTime } from "../ops-console/OpsShared";
import { IntelligenceSpectrumSkeleton, IntelligenceTableSkeleton } from "./IntelligenceDataSkeleton";

const EMPTY_KPIS = {
  eligible_publications: 0,
  unmatched_count: 0,
  needs_review_count: 0,
  approved_count: 0,
  rejected_count: 0,
  overridden_count: 0,
  stale_count: 0,
};

function MatchingToolbarGlyph({ kind }: { kind: "search" | "refresh" | "spark" | "chevron" | "check" | "close" | "shield" }) {
  if (kind === "search") {
    return (
      <svg aria-hidden="true" className="affiliate-matching-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="6.25" stroke="currentColor" strokeWidth="1.85" />
        <path d="m16.1 16.1 4.1 4.1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "spark") {
    return (
      <svg aria-hidden="true" className="affiliate-matching-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M12 4.2 13 8.8 17.5 9.8 13 10.8 12 15.4 11 10.8 6.5 9.8 11 8.8Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "chevron") {
    return (
      <svg aria-hidden="true" className="affiliate-matching-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="m9 10.5 3 3 3-3" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "check") {
    return (
      <svg aria-hidden="true" className="affiliate-matching-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="m6.8 12.2 3.2 3.2 7.2-7.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "close") {
    return (
      <svg aria-hidden="true" className="affiliate-matching-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="m7.5 7.5 9 9M16.5 7.5l-9 9" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "shield") {
    return (
      <svg aria-hidden="true" className="affiliate-matching-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M12 3.6 19 6.2v5.1c0 4.4-2.9 7.5-7 8.9-4.1-1.4-7-4.5-7-8.9V6.2L12 3.6Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
        <path d="m9.4 12.1 1.8 1.8 3.6-3.7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="affiliate-matching-toolbar__glyph" fill="none" viewBox="0 0 24 24">
      <path d="M19.2 8.2V12h-3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M4.8 15.8V12h3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M7.05 9.15a6.2 6.2 0 0 1 10.4-1.75L19.2 9.15M4.8 14.85l1.75 1.75a6.2 6.2 0 0 0 10.4-1.75" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
    </svg>
  );
}

export function AffiliateProductMatchingQueue() {
  const t = useT();
  const { notify } = useNotice();
  const [queue, setQueue] = useState({ items: [] as AffiliateProductMatchQueueItem[], total: 0, kpis: EMPTY_KPIS });
  const [catalog, setCatalog] = useState<AffiliateProduct[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedProducts, setSelectedProducts] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [overrideMode, setOverrideMode] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchAffiliateProductMatchQueue({
        decisionStatus: statusFilter || undefined,
        query: query || undefined,
        limit: 100,
      });
      setQueue(payload);
      setHasLoadedOnce(true);
      setError(null);
      if (showNotice) notify({ message: t("affiliateMatching.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateMatching.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    void fetchAffiliateProducts({ activeOnly: true, limit: 500 })
      .then((payload) => setCatalog(payload.products))
      .catch(() => undefined);
    const timer = setInterval(() => void load(), 15_000);
    return () => clearInterval(timer);
  }, [statusFilter, query]);

  function openItem(item: AffiliateProductMatchQueueItem) {
    const current = item.product_match?.suggestions[0]?.product_id ?? "";
    setExpandedId((value) => (value === item.platform_publication_id ? null : item.platform_publication_id));
    if (current && !selectedProducts[item.platform_publication_id]) {
      setSelectedProducts((values) => ({ ...values, [item.platform_publication_id]: current }));
    }
  }

  async function run(item: AffiliateProductMatchQueueItem) {
    setBusy(`run-${item.platform_publication_id}`);
    setError(null);
    try {
      const result = await runAffiliateProductMatch(item.platform_publication_id);
      notify({
        message: result.product_match
          ? t("affiliateMatching.alreadyCurrent")
          : t("affiliateMatching.queued").replace("{id}", result.job?.id.slice(0, 8) ?? "—"),
        tone: result.product_match ? "info" : "success",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateMatching.runError"));
    } finally {
      setBusy(null);
    }
  }

  async function decide(item: AffiliateProductMatchQueueItem, decision: "APPROVED" | "REJECTED" | "OVERRIDDEN") {
    if (!item.product_match) return;
    const selected = selectedProducts[item.platform_publication_id] || null;
    if ((decision === "APPROVED" || decision === "OVERRIDDEN") && !selected) return;
    if ((decision === "REJECTED" || decision === "OVERRIDDEN") && !reasons[item.platform_publication_id]?.trim()) return;
    setBusy(`${decision}-${item.platform_publication_id}`);
    setError(null);
    try {
      await decideAffiliateProductMatch(item.product_match.id, {
        decision,
        selected_product_id: selected,
        reason: reasons[item.platform_publication_id]?.trim() || null,
      });
      const messageKey = decision === "APPROVED" ? "approvedMessage" : decision === "REJECTED" ? "rejectedMessage" : "overriddenMessage";
      notify({ message: t(`affiliateMatching.${messageKey}`), tone: "success" });
      setExpandedId(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateMatching.decisionError"));
    } finally {
      setBusy(null);
    }
  }

  const kpis = queue.kpis;
  const statusTotal = Math.max(
    kpis.unmatched_count + kpis.needs_review_count + kpis.approved_count + kpis.rejected_count + kpis.overridden_count,
    kpis.eligible_publications,
    1,
  );
  const unmatchedDeg = (kpis.unmatched_count / statusTotal) * 360;
  const reviewDeg = (kpis.needs_review_count / statusTotal) * 360;
  const approvedDeg = (kpis.approved_count / statusTotal) * 360;
  const rejectedDeg = (kpis.rejected_count / statusTotal) * 360;
  const overriddenDeg = (kpis.overridden_count / statusTotal) * 360;
  const donutGradient =
    kpis.eligible_publications === 0
      ? "conic-gradient(#d5e0db 0deg 90deg, #c5d4ce 90deg 180deg, #b7c7c0 180deg 270deg, #a9bab3 270deg 360deg)"
      : `conic-gradient(#6f857c 0deg ${unmatchedDeg}deg, #c4841a ${unmatchedDeg}deg ${unmatchedDeg + reviewDeg}deg, #2f8f6f ${unmatchedDeg + reviewDeg}deg ${unmatchedDeg + reviewDeg + approvedDeg}deg, #ac4337 ${unmatchedDeg + reviewDeg + approvedDeg}deg ${unmatchedDeg + reviewDeg + approvedDeg + rejectedDeg}deg, #6b7bb8 ${unmatchedDeg + reviewDeg + approvedDeg + rejectedDeg}deg ${unmatchedDeg + reviewDeg + approvedDeg + rejectedDeg + overriddenDeg}deg, #d5e0db ${unmatchedDeg + reviewDeg + approvedDeg + rejectedDeg + overriddenDeg}deg 360deg)`;
  const barScale = Math.max(kpis.eligible_publications, 1);
  const statusLegend = [
    {
      key: "unmatched" as const,
      label: t("affiliateMatching.unmatched"),
      count: kpis.unmatched_count,
      pct: Math.round((kpis.unmatched_count / statusTotal) * 100),
    },
    {
      key: "review" as const,
      label: t("affiliateMatching.needsReview"),
      count: kpis.needs_review_count,
      pct: Math.round((kpis.needs_review_count / statusTotal) * 100),
    },
    {
      key: "approved" as const,
      label: t("affiliateMatching.approved"),
      count: kpis.approved_count,
      pct: Math.round((kpis.approved_count / statusTotal) * 100),
    },
    {
      key: "rejected" as const,
      label: t("affiliateMatching.rejected"),
      count: kpis.rejected_count,
      pct: Math.round((kpis.rejected_count / statusTotal) * 100),
    },
    {
      key: "overridden" as const,
      label: t("affiliateMatching.overridden"),
      count: kpis.overridden_count,
      pct: Math.round((kpis.overridden_count / statusTotal) * 100),
    },
  ];
  const signalBars = [
    {
      key: "unmatched" as const,
      label: t("affiliateMatching.unmatched"),
      count: kpis.unmatched_count,
      filter: "UNMATCHED",
    },
    {
      key: "review" as const,
      label: t("affiliateMatching.needsReview"),
      count: kpis.needs_review_count,
      filter: "NEEDS_REVIEW",
    },
    {
      key: "approved" as const,
      label: t("affiliateMatching.approved"),
      count: kpis.approved_count,
      filter: "APPROVED",
    },
    {
      key: "rejected" as const,
      label: t("affiliateMatching.rejected"),
      count: kpis.rejected_count,
      filter: "REJECTED",
    },
    {
      key: "overridden" as const,
      label: t("affiliateMatching.overridden"),
      count: kpis.overridden_count,
      filter: "OVERRIDDEN",
    },
  ];
  const coldLoading = loading && !hasLoadedOnce;
  const activeItem = queue.items.find((item) => item.platform_publication_id === expandedId) ?? null;
  const activeMatch = activeItem?.product_match ?? null;
  const activeSelectedId =
    activeItem && activeMatch
      ? selectedProducts[activeItem.platform_publication_id] ?? activeMatch.suggestions[0]?.product_id ?? ""
      : "";
  const activeSuggestion =
    activeMatch?.suggestions.find((suggestion) => suggestion.product_id === activeSelectedId) ??
    activeMatch?.suggestions[0] ??
    null;
  const activeCatalogProduct = activeSelectedId ? catalog.find((product) => product.id === activeSelectedId) ?? null : null;
  const factName = activeSuggestion?.product_name ?? activeCatalogProduct?.name ?? null;
  const factMerchant = activeSuggestion?.merchant_name ?? activeCatalogProduct?.merchant_name ?? null;
  const factPlatform = activeSuggestion?.platform ?? activeCatalogProduct?.platform ?? null;
  const factPrice =
    activeSuggestion?.price_amount != null
      ? `${activeSuggestion.currency_code} ${activeSuggestion.price_amount}`
      : activeCatalogProduct?.price_amount != null
        ? `${activeCatalogProduct.currency_code} ${activeCatalogProduct.price_amount}`
        : null;
  const factCommission =
    activeSuggestion?.commission_rate_percent != null
      ? `${activeSuggestion.commission_rate_percent}%`
      : activeCatalogProduct?.commission_rate_percent != null
        ? `${activeCatalogProduct.commission_rate_percent}%`
        : null;
  const factAvailability = activeSuggestion?.availability_status ?? activeCatalogProduct?.availability_status ?? null;
  const scoreBreakdown = activeSuggestion ? Object.entries(activeSuggestion.score_breakdown) : [];

  return (
    <section className="affiliate-matching-page is-v10 is-v11 is-v12 is-v13 is-v14 is-v15 is-v16 is-v17 is-v18 is-v19 is-v20 is-v21 is-v22 is-v23 is-v24">
      {error ? (
        <div className="inline-error" role="alert">
          {error}
        </div>
      ) : null}

      {coldLoading ? (
        <IntelligenceSpectrumSkeleton className="affiliate-matching-spectrum" label={t("affiliateMatching.loading")} />
      ) : (
      <section aria-label={t("affiliateMatching.spectrumStatusMix")} className="affiliate-matching-spectrum">
        <div className="affiliate-matching-spectrum__stage">
          <header className="affiliate-matching-spectrum__head">
            <span className="affiliate-matching-spectrum__eyebrow">{t("affiliateMatching.spectrumStatusMix")}</span>
            <small className="affiliate-matching-spectrum__hint">{t("affiliateMatching.eligibleHint")}</small>
          </header>

          <div className="affiliate-matching-spectrum__status">
            <div aria-hidden="true" className="affiliate-matching-spectrum__donut" style={{ background: donutGradient }}>
              <div className="affiliate-matching-spectrum__donut-core">
                <b>{kpis.eligible_publications}</b>
                <small>{t("affiliateMatching.eligible")}</small>
              </div>
            </div>
            <ul className="affiliate-matching-spectrum__legend" aria-label={t("affiliateMatching.status")}>
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

          <div className="affiliate-matching-spectrum__attention">
            <span className="affiliate-matching-spectrum__attention-label">{t("affiliateMatching.spectrumAttention")}</span>
            <div className="affiliate-matching-spectrum__plot" role="list">
              {signalBars.map((bar) => {
                const barW = bar.count === 0 ? 0 : Math.max(8, Math.round((bar.count / barScale) * 100));
                const active = statusFilter === bar.filter;
                return (
                  <button
                    aria-label={`${bar.label}: ${bar.count}`}
                    aria-pressed={active}
                    className={`is-${bar.key}${bar.count === 0 ? " is-empty" : ""}${active ? " is-current" : ""}`}
                    key={bar.key}
                    onClick={() => setStatusFilter(active ? "" : bar.filter)}
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

      <section className="affiliate-matching-toolbar is-v12" aria-label={t("affiliateMatching.title")}>
        <select
          aria-label={t("affiliateMatching.status")}
          onChange={(event) => setStatusFilter(event.target.value)}
          value={statusFilter}
        >
          <option value="">{t("affiliateMatching.allStatuses")}</option>
          <option value="UNMATCHED">{t("affiliateMatching.unmatched")}</option>
          <option value="NEEDS_REVIEW">{t("affiliateMatching.needsReview")}</option>
          <option value="APPROVED">{t("affiliateMatching.approved")}</option>
          <option value="REJECTED">{t("affiliateMatching.rejected")}</option>
          <option value="OVERRIDDEN">{t("affiliateMatching.overridden")}</option>
        </select>
        <form
          className="affiliate-matching-toolbar__search"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(queryInput.trim());
          }}
        >
          <input
            aria-label={t("affiliateMatching.search")}
            onChange={(event) => setQueryInput(event.target.value)}
            placeholder={t("affiliateMatching.searchPlaceholder")}
            value={queryInput}
          />
          <AsyncButton
            aria-label={t("affiliateMatching.apply")}
            className="affiliate-matching-toolbar__icon-btn is-apply"
            leadingIcon={<MatchingToolbarGlyph kind="search" />}
            pending={loading}
            pendingLabel={<span className="visually-hidden">{t("affiliateMatching.apply")}</span>}
            title={t("affiliateMatching.apply")}
            type="submit"
          >
            <span className="visually-hidden">{t("affiliateMatching.apply")}</span>
          </AsyncButton>
        </form>
        <button
          aria-label={t("affiliateMatching.noAutoPlacement")}
          className="affiliate-matching-toolbar__safety"
          title={t("affiliateMatching.noAutoPlacement")}
          type="button"
        >
          <MatchingToolbarGlyph kind="shield" />
          <span className="visually-hidden">{t("affiliateMatching.noAutoPlacement")}</span>
        </button>
        <AsyncButton
          aria-label={t("common.refresh")}
          className="affiliate-matching-toolbar__icon-btn is-refresh"
          leadingIcon={<MatchingToolbarGlyph kind="refresh" />}
          pending={loading}
          pendingLabel={<span className="visually-hidden">{t("common.refresh")}</span>}
          title={t("common.refresh")}
          onClick={() => void load(true)}
        >
          <span className="visually-hidden">{t("common.refresh")}</span>
        </AsyncButton>
      </section>

      <section className="affiliate-matching-table-wrap is-v13" aria-label={t("affiliateMatching.results").replace("{count}", String(queue.total))}>
        <header className="affiliate-matching-results-head is-v13">
          <div className="affiliate-matching-results-head__title">
            <strong>{t("affiliateMatching.results").replace("{count}", String(queue.total))}</strong>
          </div>
          {!coldLoading ? (
            <span className="affiliate-matching-results-head__stale" title={t("affiliateMatching.staleHint")}>
              <em>{t("affiliateMatching.stale")}</em>
              <b>{kpis.stale_count}</b>
            </span>
          ) : null}
        </header>

        {coldLoading ? (
          <IntelligenceTableSkeleton className="affiliate-matching-loading" label={t("affiliateMatching.loading")} />
        ) : queue.items.length === 0 ? (
          <section className="affiliate-matching-empty">
            <strong>{t("affiliateMatching.empty")}</strong>
            <small>{t("affiliateMatching.emptyHint")}</small>
          </section>
        ) : (
          <table className="affiliate-matching-table is-v13">
            <thead>
              <tr>
                <th>{t("affiliateMatching.reel")}</th>
                <th>{t("affiliateMatching.topic")}</th>
                <th>{t("affiliateMatching.topProduct")}</th>
                <th>{t("affiliateMatching.fitScore")}</th>
                <th>{t("affiliateMatching.status")}</th>
                <th>{t("affiliateMatching.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {queue.items.map((item) => {
                const match = item.product_match;
                const top = match?.suggestions[0];
                const open = expandedId === item.platform_publication_id;
                const jobActive = Boolean(item.latest_job && ["QUEUED", "RUNNING", "RETRYABLE"].includes(item.latest_job.status));
                const runLabel = match ? t("affiliateMatching.rerun") : t("affiliateMatching.match");

                return (
                  <tr
                    className={[open ? "is-open" : "", match ? "is-clickable" : ""].filter(Boolean).join(" ") || undefined}
                    key={item.platform_publication_id}
                    onClick={match ? () => openItem(item) : undefined}
                  >
                    <td>
                      <div className="affiliate-matching-reel">
                        {item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span>Reel</span>}
                        <div className="affiliate-matching-reel__copy">
                          <strong>{item.caption || item.external_reel_id || "Reel"}</strong>
                          <small>{item.published_at ? formatDateTime(item.published_at) : item.external_reel_id}</small>
                          <small>{item.page_display_name}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="affiliate-matching-topic">
                        <strong>{item.primary_topic_name || item.primary_topic_code || "—"}</strong>
                        {item.classification_status ? <small>{item.classification_status}</small> : null}
                      </div>
                    </td>
                    <td>
                      {top ? (
                        <div className="affiliate-matching-product">
                          <strong>{top.product_name}</strong>
                          <small>
                            {top.platform} · {top.commission_rate_percent == null ? "—" : `${top.commission_rate_percent}%`}
                          </small>
                        </div>
                      ) : (
                        <small className="muted">{match ? t("affiliateMatching.noSuggestion") : t("affiliateMatching.notRun")}</small>
                      )}
                    </td>
                    <td>
                      {top ? (
                        <b className={`affiliate-fit-score is-${top.affiliate_fit_score >= 70 ? "high" : top.affiliate_fit_score >= 45 ? "medium" : "low"}`}>
                          {Math.round(top.affiliate_fit_score)}
                        </b>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {match ? (
                        <span className={`affiliate-matching-status is-${match.decision_status.toLowerCase()}`}>
                          {t(`affiliateMatching.statusValue.${match.decision_status}`)}
                        </span>
                      ) : item.latest_job ? (
                        <span className="affiliate-matching-status is-running">
                          {item.latest_job.status} · {item.latest_job.progress_percent}%
                        </span>
                      ) : (
                        <span className="affiliate-matching-status is-unmatched">{t("affiliateMatching.unmatched")}</span>
                      )}
                    </td>
                    <td onClick={(event) => event.stopPropagation()}>
                      <div className="affiliate-matching-actions">
                        <AsyncButton
                          aria-label={runLabel}
                          className="affiliate-matching-actions__icon-btn is-run"
                          disabled={jobActive}
                          leadingIcon={<MatchingToolbarGlyph kind={match ? "refresh" : "spark"} />}
                          pending={busy === `run-${item.platform_publication_id}`}
                          pendingLabel={<span className="visually-hidden">{runLabel}</span>}
                          title={runLabel}
                          onClick={() => void run(item)}
                        >
                          <span className="visually-hidden">{runLabel}</span>
                        </AsyncButton>
                        {match ? (
                          <button
                            aria-expanded={open}
                            aria-haspopup="dialog"
                            aria-label={open ? t("affiliateMatching.closeReview") : t("affiliateMatching.review")}
                            className={`affiliate-matching-actions__icon-btn is-review${open ? " is-open" : ""}`}
                            title={open ? t("affiliateMatching.closeReview") : t("affiliateMatching.review")}
                            type="button"
                            onClick={() => openItem(item)}
                          >
                            <MatchingToolbarGlyph kind="chevron" />
                          </button>
                        ) : null}
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
        eyebrow={t("affiliateMatching.review")}
        footer={
          activeItem && activeMatch ? (
            <div className="affiliate-matching-review__footer">
              <div className="affiliate-matching-review__actions">
                <AsyncButton
                  className="affiliate-matching-review__btn is-reject"
                  leadingIcon={<MatchingToolbarGlyph kind="close" />}
                  pending={busy === `REJECTED-${activeItem.platform_publication_id}`}
                  onClick={() => void decide(activeItem, "REJECTED")}
                >
                  {t("affiliateMatching.reject")}
                </AsyncButton>
                <AsyncButton
                  className="affiliate-matching-review__btn is-approve"
                  disabled={!activeSelectedId || overrideMode[activeItem.platform_publication_id]}
                  leadingIcon={<MatchingToolbarGlyph kind="check" />}
                  pending={busy === `APPROVED-${activeItem.platform_publication_id}`}
                  onClick={() => void decide(activeItem, "APPROVED")}
                >
                  {t("affiliateMatching.approve")}
                </AsyncButton>
                <AsyncButton
                  className="primary affiliate-matching-review__btn is-override"
                  disabled={
                    !activeSelectedId ||
                    !overrideMode[activeItem.platform_publication_id] ||
                    !reasons[activeItem.platform_publication_id]?.trim()
                  }
                  leadingIcon={<MatchingToolbarGlyph kind="spark" />}
                  pending={busy === `OVERRIDDEN-${activeItem.platform_publication_id}`}
                  onClick={() => void decide(activeItem, "OVERRIDDEN")}
                >
                  {t("affiliateMatching.override")}
                </AsyncButton>
              </div>
              <small className="affiliate-matching-review__safety" title={t("affiliateMatching.reviewSafety")}>
                {t("affiliateMatching.reviewSafety")}
              </small>
            </div>
          ) : null
        }
        headerExtra={
          activeItem && activeMatch ? (
            <div className="affiliate-matching-review__header-extra">
              <span className="affiliate-matching-review__version">{activeMatch.matcher_version}</span>
              <p className="affiliate-matching-review__context">
                <strong>{activeItem.caption || activeItem.external_reel_id || "Reel"}</strong>
                <span>{activeItem.primary_topic_name || activeItem.primary_topic_code || "—"}</span>
              </p>
            </div>
          ) : null
        }
        open={Boolean(activeItem && activeMatch)}
        title={t("affiliateMatching.reviewTitle")}
        titleId="affiliate-matching-review-title"
        onClose={() => setExpandedId(null)}
      >
        {activeItem && activeMatch ? (
          <div className="affiliate-matching-review is-v24">
            <span className="affiliate-matching-review__hint visually-hidden">{t("affiliateMatching.reviewHint")}</span>
            <div className="affiliate-matching-review__inspector">
              <section className="affiliate-matching-review__reel" aria-label={t("affiliateMatching.reel")}>
                <span className="affiliate-matching-review__eyebrow">{t("affiliateMatching.reel")}</span>
                <div className="affiliate-matching-review__reel-card">
                  {activeItem.thumbnail_url ? (
                    <img alt="" className="affiliate-matching-review__thumb" src={activeItem.thumbnail_url} />
                  ) : (
                    <span className="affiliate-matching-review__thumb is-empty">Reel</span>
                  )}
                  <div className="affiliate-matching-review__reel-copy">
                    <strong>{activeItem.page_display_name || "—"}</strong>
                    <small>{activeItem.external_reel_id || activeItem.platform_publication_id.slice(0, 8)}</small>
                    <span>
                      {activeItem.published_at ? formatDateTime(activeItem.published_at) : "—"}
                      {activeItem.classification_status ? ` · ${activeItem.classification_status}` : ""}
                    </span>
                  </div>
                </div>
              </section>

              <section className="affiliate-matching-review__picks" aria-label={t("affiliateMatching.topProduct")}>
                <span className="affiliate-matching-review__eyebrow">{t("affiliateMatching.topProduct")}</span>
                <div className="affiliate-matching-suggestions">
                  {activeMatch.suggestions.length ? (
                    activeMatch.suggestions.map((suggestion) => {
                      const breakdown = Object.entries(suggestion.score_breakdown);
                      const visibleBreakdown = breakdown.slice(0, 3);
                      const hiddenBreakdown = breakdown.length - visibleBreakdown.length;
                      return (
                        <label
                          className={activeSelectedId === suggestion.product_id ? "is-selected" : ""}
                          key={suggestion.product_id}
                        >
                          <input
                            checked={activeSelectedId === suggestion.product_id}
                            name={`product-${activeItem.platform_publication_id}`}
                            type="radio"
                            onChange={() =>
                              setSelectedProducts((values) => ({
                                ...values,
                                [activeItem.platform_publication_id]: suggestion.product_id,
                              }))
                            }
                          />
                          <div className="affiliate-matching-suggestions__body">
                            <div className="affiliate-matching-suggestions__title">
                              <em className="affiliate-matching-suggestions__rank">#{suggestion.rank}</em>
                              <strong>{suggestion.product_name}</strong>
                              <b className="affiliate-matching-suggestions__score">
                                {Math.round(suggestion.affiliate_fit_score)}
                              </b>
                            </div>
                            <small>{suggestion.evidence.join(" · ") || t("affiliateMatching.noEvidence")}</small>
                            <span>
                              {visibleBreakdown.map(([key, value]) => (
                                <em key={key}>
                                  {t(`affiliateMatching.score.${key}`)} {Math.round(value)}
                                </em>
                              ))}
                              {hiddenBreakdown > 0 ? <em>+{hiddenBreakdown}</em> : null}
                            </span>
                          </div>
                        </label>
                      );
                    })
                  ) : (
                    <p className="muted">{t("affiliateMatching.noSuggestion")}</p>
                  )}
                </div>
              </section>

              {factName ? (
                <section className="affiliate-matching-review__facts" aria-label={t("affiliateMatching.reviewProductFacts")}>
                  <span className="affiliate-matching-review__eyebrow">{t("affiliateMatching.reviewProductFacts")}</span>
                  <div className="affiliate-matching-review__facts-grid">
                    <div>
                      <span>{t("affiliateMatching.topProduct")}</span>
                      <strong>{factName}</strong>
                    </div>
                    <div>
                      <span>{t("affiliateMatching.reviewMerchant")}</span>
                      <strong>{factMerchant || "—"}</strong>
                    </div>
                    <div>
                      <span>{t("affiliateMatching.score.platform_compatibility")}</span>
                      <strong>{factPlatform || "—"}</strong>
                    </div>
                    <div>
                      <span>{t("affiliateMatching.reviewPrice")}</span>
                      <strong>{factPrice || "—"}</strong>
                    </div>
                    <div>
                      <span>{t("affiliateMatching.reviewCommission")}</span>
                      <strong>{factCommission || "—"}</strong>
                    </div>
                    <div>
                      <span>{t("affiliateMatching.reviewAvailability")}</span>
                      <strong>{factAvailability || "—"}</strong>
                    </div>
                  </div>
                </section>
              ) : null}

              {scoreBreakdown.length ? (
                <section className="affiliate-matching-review__breakdown" aria-label={t("affiliateMatching.reviewScoreBreakdown")}>
                  <span className="affiliate-matching-review__eyebrow">{t("affiliateMatching.reviewScoreBreakdown")}</span>
                  <ul className="affiliate-matching-review__breakdown-list">
                    {scoreBreakdown.map(([key, value]) => (
                      <li key={key} style={{ ["--score-pct" as string]: `${Math.max(0, Math.min(100, value))}%` }}>
                        <span>{t(`affiliateMatching.score.${key}`)}</span>
                        <b>{Math.round(value)}</b>
                        <i />
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <section className="affiliate-matching-review__meta" aria-label={t("affiliateMatching.reviewMatchMeta")}>
                <span className="affiliate-matching-review__eyebrow">{t("affiliateMatching.reviewMatchMeta")}</span>
                <div className="affiliate-matching-review__meta-grid">
                  <div>
                    <span>{t("affiliateMatching.status")}</span>
                    <strong>{t(`affiliateMatching.statusValue.${activeMatch.decision_status}`)}</strong>
                  </div>
                  <div>
                    <span>{t("affiliateMatching.reviewCatalog")}</span>
                    <strong>{activeMatch.catalog_version}</strong>
                  </div>
                  <div>
                    <span>{t("affiliateMatching.reviewCreated")}</span>
                    <strong>{formatDateTime(activeMatch.created_at)}</strong>
                  </div>
                </div>
              </section>

              <section className="affiliate-matching-review__decide" aria-label={t("affiliateMatching.reviewDecide")}>
                <span className="affiliate-matching-review__eyebrow">{t("affiliateMatching.reviewDecide")}</span>
                <div className="affiliate-matching-review__fields">
                  <label className="affiliate-matching-override">
                    <span>{t("affiliateMatching.overrideProduct")}</span>
                    <select
                      onChange={(event) => {
                        setSelectedProducts((values) => ({
                          ...values,
                          [activeItem.platform_publication_id]: event.target.value,
                        }));
                        setOverrideMode((values) => ({ ...values, [activeItem.platform_publication_id]: true }));
                      }}
                      value={overrideMode[activeItem.platform_publication_id] ? activeSelectedId : ""}
                    >
                      <option value="">{t("affiliateMatching.chooseOverride")}</option>
                      {catalog.map((product) => (
                        <option key={product.id} value={product.id}>
                          {product.name} · {product.platform}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="affiliate-matching-reason">
                    <span>{t("affiliateMatching.reason")}</span>
                    <textarea
                      onChange={(event) =>
                        setReasons((values) => ({
                          ...values,
                          [activeItem.platform_publication_id]: event.target.value,
                        }))
                      }
                      placeholder={t("affiliateMatching.reasonPlaceholder")}
                      rows={2}
                      value={reasons[activeItem.platform_publication_id] ?? ""}
                    />
                  </label>
                </div>
              </section>
            </div>
          </div>
        ) : null}
      </WorkItemDetailsDrawer>
    </section>
  );
}
