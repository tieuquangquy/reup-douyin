"use client";

import { Fragment, useEffect, useState } from "react";
import { decideAffiliateProductMatch, fetchAffiliateProductMatchQueue, fetchAffiliateProducts, runAffiliateProductMatch } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { AffiliateProduct, AffiliateProductMatchQueueItem } from "../../types/affiliate";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { formatDateTime } from "../ops-console/OpsShared";


const EMPTY_KPIS = { eligible_publications: 0, unmatched_count: 0, needs_review_count: 0, approved_count: 0, rejected_count: 0, stale_count: 0 };


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
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchAffiliateProductMatchQueue({ decisionStatus: statusFilter || undefined, query: query || undefined, limit: 100 });
      setQueue(payload);
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
    void fetchAffiliateProducts({ activeOnly: true, limit: 500 }).then((payload) => setCatalog(payload.products)).catch(() => undefined);
    const timer = setInterval(() => void load(), 15_000);
    return () => clearInterval(timer);
  }, [statusFilter, query]);

  function openItem(item: AffiliateProductMatchQueueItem) {
    const current = item.product_match?.suggestions[0]?.product_id ?? "";
    setExpandedId((value) => value === item.platform_publication_id ? null : item.platform_publication_id);
    if (current && !selectedProducts[item.platform_publication_id]) setSelectedProducts((values) => ({ ...values, [item.platform_publication_id]: current }));
  }

  async function run(item: AffiliateProductMatchQueueItem) {
    setBusy(`run-${item.platform_publication_id}`);
    setError(null);
    try {
      const result = await runAffiliateProductMatch(item.platform_publication_id);
      notify({ message: result.product_match ? t("affiliateMatching.alreadyCurrent") : t("affiliateMatching.queued").replace("{id}", result.job?.id.slice(0, 8) ?? "—"), tone: result.product_match ? "info" : "success" });
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
      await decideAffiliateProductMatch(item.product_match.id, { decision, selected_product_id: selected, reason: reasons[item.platform_publication_id]?.trim() || null });
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
  return <section className="affiliate-matching-page">
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    <section className="affiliate-matching-kpis"><article><span>{t("affiliateMatching.eligible")}</span><strong>{kpis.eligible_publications}</strong><small>{t("affiliateMatching.eligibleHint")}</small></article><article className="is-warning"><span>{t("affiliateMatching.unmatched")}</span><strong>{kpis.unmatched_count}</strong><small>{t("affiliateMatching.unmatchedHint")}</small></article><article className="is-warning"><span>{t("affiliateMatching.needsReview")}</span><strong>{kpis.needs_review_count}</strong><small>{t("affiliateMatching.needsReviewHint")}</small></article><article className="is-good"><span>{t("affiliateMatching.approved")}</span><strong>{kpis.approved_count}</strong><small>{t("affiliateMatching.approvedHint")}</small></article><article><span>{t("affiliateMatching.stale")}</span><strong>{kpis.stale_count}</strong><small>{t("affiliateMatching.staleHint")}</small></article></section>
    <section className="affiliate-matching-toolbar"><label><span>{t("affiliateMatching.status")}</span><select onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value="">{t("affiliateMatching.allStatuses")}</option><option value="UNMATCHED">{t("affiliateMatching.unmatched")}</option><option value="NEEDS_REVIEW">{t("affiliateMatching.needsReview")}</option><option value="APPROVED">{t("affiliateMatching.approved")}</option><option value="REJECTED">{t("affiliateMatching.rejected")}</option><option value="OVERRIDDEN">{t("affiliateMatching.overridden")}</option></select></label><form onSubmit={(event) => { event.preventDefault(); setQuery(queryInput.trim()); }}><label><span>{t("affiliateMatching.search")}</span><input onChange={(event) => setQueryInput(event.target.value)} placeholder={t("affiliateMatching.searchPlaceholder")} value={queryInput} /></label><AsyncButton pending={loading} type="submit">{t("affiliateMatching.apply")}</AsyncButton></form><AsyncButton pending={loading} onClick={() => void load(true)}>{t("common.refresh")}</AsyncButton></section>
    <section className="affiliate-matching-table-wrap"><header><div><strong>{t("affiliateMatching.title")}</strong><small>{t("affiliateMatching.results").replace("{count}", String(queue.total))}</small></div><span className="affiliate-matching-safety-note">{t("affiliateMatching.noAutoPlacement")}</span></header>{loading && queue.items.length === 0 ? <p className="muted">{t("affiliateMatching.loading")}</p> : queue.items.length === 0 ? <p className="muted">{t("affiliateMatching.empty")}</p> : <table className="affiliate-matching-table"><thead><tr><th>{t("affiliateMatching.reel")}</th><th>{t("affiliateMatching.topic")}</th><th>{t("affiliateMatching.topProduct")}</th><th>{t("affiliateMatching.fitScore")}</th><th>{t("affiliateMatching.status")}</th><th>{t("affiliateMatching.actions")}</th></tr></thead><tbody>{queue.items.map((item) => { const match = item.product_match; const top = match?.suggestions[0]; const open = expandedId === item.platform_publication_id; const selectedId = selectedProducts[item.platform_publication_id] ?? top?.product_id ?? ""; const jobActive = Boolean(item.latest_job && ["QUEUED", "RUNNING", "RETRYABLE"].includes(item.latest_job.status)); return <Fragment key={item.platform_publication_id}><tr><td><div className="affiliate-matching-reel">{item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span>Reel</span>}<div><strong>{item.caption || item.external_reel_id || "Reel"}</strong><small>{item.published_at ? formatDateTime(item.published_at) : item.external_reel_id}</small><small>{item.page_display_name}</small></div></div></td><td><strong>{item.primary_topic_name || item.primary_topic_code || "—"}</strong><small>{item.classification_status}</small></td><td>{top ? <div className="affiliate-matching-product"><strong>{top.product_name}</strong><small>{top.platform} · {top.commission_rate_percent == null ? "—" : `${top.commission_rate_percent}%`}</small></div> : <small className="muted">{match ? t("affiliateMatching.noSuggestion") : t("affiliateMatching.notRun")}</small>}</td><td>{top ? <b className={`affiliate-fit-score is-${top.affiliate_fit_score >= 70 ? "high" : top.affiliate_fit_score >= 45 ? "medium" : "low"}`}>{Math.round(top.affiliate_fit_score)}</b> : "—"}</td><td>{match ? <span className={`affiliate-matching-status is-${match.decision_status.toLowerCase()}`}>{t(`affiliateMatching.statusValue.${match.decision_status}`)}</span> : item.latest_job ? <span className="affiliate-matching-status is-running">{item.latest_job.status} · {item.latest_job.progress_percent}%</span> : <span className="affiliate-matching-status is-unmatched">{t("affiliateMatching.unmatched")}</span>}</td><td><div className="affiliate-matching-actions"><AsyncButton disabled={jobActive} pending={busy === `run-${item.platform_publication_id}`} onClick={() => void run(item)}>{match ? t("affiliateMatching.rerun") : t("affiliateMatching.match")}</AsyncButton>{match ? <button onClick={() => openItem(item)} type="button">{open ? t("affiliateMatching.closeReview") : t("affiliateMatching.review")}</button> : null}</div></td></tr>{open && match ? <tr className="affiliate-matching-review-row" key={`${item.platform_publication_id}-review`}><td colSpan={6}><div className="affiliate-matching-review"><header><div><strong>{t("affiliateMatching.reviewTitle")}</strong><small>{t("affiliateMatching.reviewHint")}</small></div><span>{match.matcher_version}</span></header><div className="affiliate-matching-suggestions">{match.suggestions.length ? match.suggestions.map((suggestion) => <label className={selectedId === suggestion.product_id ? "is-selected" : ""} key={suggestion.product_id}><input checked={selectedId === suggestion.product_id} name={`product-${item.platform_publication_id}`} onChange={() => setSelectedProducts((values) => ({ ...values, [item.platform_publication_id]: suggestion.product_id }))} type="radio" /><div><strong>#{suggestion.rank} · {suggestion.product_name}</strong><small>{suggestion.evidence.join(" · ") || t("affiliateMatching.noEvidence")}</small><span>{Object.entries(suggestion.score_breakdown).map(([key, value]) => <em key={key}>{t(`affiliateMatching.score.${key}`)} {Math.round(value)}</em>)}</span></div><b>{Math.round(suggestion.affiliate_fit_score)}</b></label>) : <p className="muted">{t("affiliateMatching.noSuggestion")}</p>}</div><label className="affiliate-matching-override"><span>{t("affiliateMatching.overrideProduct")}</span><select onChange={(event) => { setSelectedProducts((values) => ({ ...values, [item.platform_publication_id]: event.target.value })); setOverrideMode((values) => ({ ...values, [item.platform_publication_id]: true })); }} value={overrideMode[item.platform_publication_id] ? selectedId : ""}><option value="">{t("affiliateMatching.chooseOverride")}</option>{catalog.map((product) => <option key={product.id} value={product.id}>{product.name} · {product.platform}</option>)}</select></label><label className="affiliate-matching-reason"><span>{t("affiliateMatching.reason")}</span><textarea onChange={(event) => setReasons((values) => ({ ...values, [item.platform_publication_id]: event.target.value }))} placeholder={t("affiliateMatching.reasonPlaceholder")} value={reasons[item.platform_publication_id] ?? ""} /></label><footer><small>{t("affiliateMatching.reviewSafety")}</small><div><AsyncButton pending={busy === `REJECTED-${item.platform_publication_id}`} onClick={() => void decide(item, "REJECTED")}>{t("affiliateMatching.reject")}</AsyncButton><AsyncButton disabled={!selectedId || overrideMode[item.platform_publication_id]} pending={busy === `APPROVED-${item.platform_publication_id}`} onClick={() => void decide(item, "APPROVED")}>{t("affiliateMatching.approve")}</AsyncButton><AsyncButton className="primary" disabled={!selectedId || !overrideMode[item.platform_publication_id] || !reasons[item.platform_publication_id]?.trim()} pending={busy === `OVERRIDDEN-${item.platform_publication_id}`} onClick={() => void decide(item, "OVERRIDDEN")}>{t("affiliateMatching.override")}</AsyncButton></div></footer></div></td></tr> : null}</Fragment>; })}</tbody></table>}</section>
  </section>;
}

