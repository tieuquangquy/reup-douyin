"use client";

import { Fragment, useEffect, useState } from "react";
import { fetchAffiliateOpportunityQueue, runPublicationGrowthScore } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { AffiliateOpportunityItem, AffiliateOpportunityQueueResponse } from "../../types/growth-intelligence";
import { formatDateTime } from "../ops-console/OpsShared";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { AffiliateCommentPlacementPanel } from "./AffiliateCommentPlacementPanel";


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


export function AffiliateOpportunityRanking() {
  const t = useT();
  const { notify } = useNotice();
  const [queue, setQueue] = useState<AffiliateOpportunityQueueResponse>(EMPTY_QUEUE);
  const [recommendation, setRecommendation] = useState("");
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
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

  return <section className="opportunity-ranking-page">
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    <section className="opportunity-ranking-kpis">
      <article><span>{t("opportunityRanking.eligible")}</span><strong>{queue.kpis.eligible_count}</strong><small>{t("opportunityRanking.eligibleHint")}</small></article>
      <article className="is-priority"><span>{t("opportunityRanking.priority")}</span><strong>{queue.kpis.priority_count}</strong><small>{t("opportunityRanking.priorityHint")}</small></article>
      <article className="is-monitor"><span>{t("opportunityRanking.monitor")}</span><strong>{queue.kpis.monitor_count}</strong><small>{t("opportunityRanking.monitorHint")}</small></article>
      <article className="is-blocked"><span>{t("opportunityRanking.doNotPlace")}</span><strong>{queue.kpis.do_not_place_count}</strong><small>{t("opportunityRanking.doNotPlaceHint")}</small></article>
      <article><span>{t("opportunityRanking.insufficient")}</span><strong>{queue.kpis.insufficient_data_count}</strong><small>{t("opportunityRanking.insufficientHint")}</small></article>
    </section>
    <section className="opportunity-ranking-toolbar">
      <label><span>{t("opportunityRanking.recommendation")}</span><select onChange={(event) => setRecommendation(event.target.value)} value={recommendation}><option value="">{t("opportunityRanking.allRecommendations")}</option><option value="PRIORITY">{t("opportunityRanking.priority")}</option><option value="MONITOR">{t("opportunityRanking.monitor")}</option><option value="DO_NOT_PLACE">{t("opportunityRanking.doNotPlace")}</option><option value="INSUFFICIENT_DATA">{t("opportunityRanking.insufficient")}</option></select></label>
      <form onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()); }}><label><span>{t("opportunityRanking.search")}</span><input onChange={(event) => setQueryInput(event.target.value)} placeholder={t("opportunityRanking.searchPlaceholder")} value={queryInput} /></label><AsyncButton pending={loading} type="submit">{t("opportunityRanking.apply")}</AsyncButton></form>
      <AsyncButton pending={loading} onClick={() => void load(true)}>{t("common.refresh")}</AsyncButton>
    </section>
    <section className="opportunity-ranking-table-wrap">
      <header><div><strong>{t("opportunityRanking.title")}</strong><small>{t("opportunityRanking.results").replace("{count}", String(queue.total))}</small></div></header>
      {loading && queue.items.length === 0 ? <p className="muted opportunity-ranking-empty">{t("opportunityRanking.loading")}</p> : queue.items.length === 0 ? <p className="muted opportunity-ranking-empty">{t("opportunityRanking.empty")}</p> : <table className="opportunity-ranking-table"><thead><tr><th>{t("opportunityRanking.reel")}</th><th>{t("opportunityRanking.product")}</th><th>{t("opportunityRanking.growthScore")}</th><th>{t("opportunityRanking.affiliateFit")}</th><th>{t("opportunityRanking.recommendation")}</th><th>{t("opportunityRanking.actions")}</th></tr></thead><tbody>{queue.items.map((item) => {
        const growth = item.growth_assessment;
        const jobActive = Boolean(item.latest_job && ["QUEUED", "RUNNING", "RETRYABLE"].includes(item.latest_job.status));
        const open = expandedId === item.platform_publication_id;
        return <Fragment key={item.platform_publication_id}><tr><td><div className="opportunity-ranking-reel">{item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span>Reel</span>}<div><strong>{item.caption || item.external_reel_id || "Reel"}</strong><small>{item.page_display_name}</small><small>{item.published_at ? formatDateTime(item.published_at) : item.external_reel_id}</small></div></div></td><td><div className="opportunity-ranking-product"><strong>{item.selected_product_name}</strong><small>{item.selected_product_platform} · {item.product_match_decision}</small><span className={`is-${item.selected_product_availability.toLowerCase()}`}>{item.selected_product_availability}</span></div></td><td><div className="opportunity-score-cell"><b className={scoreClass(growth?.growth_score ?? null)}>{growth?.growth_score == null ? "—" : Math.round(growth.growth_score)}</b><small>{growth ? `${t(`opportunityRanking.confidenceValue.${growth.confidence}`)} · ${t(`opportunityRanking.growthStatus.${growth.status}`)}` : t("opportunityRanking.notScored")}</small>{item.growth_is_stale ? <em>{t("opportunityRanking.stale")}</em> : null}</div></td><td><b className={`opportunity-fit-score ${scoreClass(item.affiliate_fit_score)}`}>{item.affiliate_fit_score == null ? "—" : Math.round(item.affiliate_fit_score)}</b></td><td><div className="opportunity-recommendation-cell"><span className={`is-${item.recommendation.toLowerCase()}`}>{t(`opportunityRanking.recommendationValue.${item.recommendation}`)}</span><small>{t(`opportunityRanking.reason.${item.recommendation_reason}`)}</small></div></td><td><div className="opportunity-ranking-actions"><AsyncButton disabled={jobActive} pending={busyId === item.platform_publication_id} onClick={() => void calculate(item)}>{growth ? t("opportunityRanking.recalculate") : t("opportunityRanking.calculate")}</AsyncButton>{growth ? <button onClick={() => setExpandedId(open ? null : item.platform_publication_id)} type="button">{open ? t("opportunityRanking.close") : item.recommendation === "PRIORITY" ? t("affiliateComment.prepare") : t("opportunityRanking.breakdown")}</button> : null}<a href={`/publishing/publications?account_id=${item.platform_account_id}`}>{t("opportunityRanking.openPublication")}</a></div></td></tr>{open && growth ? <tr className="opportunity-ranking-detail-row"><td colSpan={6}><section className="opportunity-ranking-detail"><header><div><strong>{t("opportunityRanking.breakdownTitle")}</strong><small>{growth.score_version} · {growth.snapshot_count} {t("opportunityRanking.snapshots")}</small></div><span>{t("opportunityRanking.noCombinedScore")}</span></header><div>{Object.entries(growth.score_breakdown).map(([key, value]) => <article key={key}><span>{t(`opportunityRanking.score.${key}`)}</span><b>{Math.round(value)}</b><small>/ {key === "view_velocity" ? 35 : key === "view_acceleration" ? 25 : key === "engagement_quality" ? 20 : 10}</small></article>)}</div><ul>{growth.evidence.map((entry) => <li key={entry}>{entry.replaceAll("_", " ")}</li>)}</ul><AffiliateCommentPlacementPanel item={item} /></section></td></tr> : null}</Fragment>;
      })}</tbody></table>}
    </section>
  </section>;
}
