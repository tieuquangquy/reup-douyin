"use client";

import { useEffect, useState } from "react";
import {
  approveAffiliateCommentPlacement,
  fetchAffiliateCommentHistory,
  fetchAffiliateCommentPlacement,
  fetchAffiliateCommentTemplates,
  fetchJob,
  previewAffiliateCommentPlacement,
  verifyAffiliateCommentPlacement,
} from "../../lib/api";
import { affiliateImagePreviewUrl } from "../../lib/affiliateImagePresentation";
import { useT } from "../../lib/i18n";
import { isPublicHttpsUrl } from "../../lib/publicHttpsUrl";
import type { AffiliateCommentHistoryResponse, AffiliateCommentPlacement, AffiliateCommentVerification } from "../../types/affiliate-comment";
import type { AffiliateCommentTemplate } from "../../types/affiliate-comment-template";
import type { AffiliateOpportunityItem } from "../../types/growth-intelligence";
import type { Job } from "../../types/jobs";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";


const DEFAULT_CTA = "Xem sản phẩm phù hợp với video tại:";
const DEFAULT_DISCLOSURE = "Link affiliate — tôi có thể nhận hoa hồng nếu bạn mua hàng.";
const DEFAULT_CUSTOM_TEMPLATE = "{{cta}}\n\n{{product_name}}\n{{description}}\n\n{{affiliate_url}}\n\n{{disclosure}}";
const CUSTOM_TEMPLATE_VARIABLES = new Set([
  "cta",
  "product_name",
  "description",
  "affiliate_url",
  "disclosure",
  "page_name",
  "reel_title",
  "topic_name",
  "product_image",
]);
const EMPTY_HISTORY: AffiliateCommentHistoryResponse = {
  placements: [],
  can_create_another: false,
  can_post_now: false,
  posted_count_24h: 0,
  max_posts_per_24h: 2,
  cooldown_hours: 6,
  next_allowed_at: null,
  blocked_reason: null,
};

function commentVerification(placement: AffiliateCommentPlacement): AffiliateCommentVerification {
  const value = placement.metadata_json?.verification;
  return value && typeof value === "object"
    ? value as AffiliateCommentVerification
    : { status: "NOT_CHECKED" };
}


export function AffiliateCommentPlacementPanel({ item }: { item: AffiliateOpportunityItem }) {
  const t = useT();
  const { notify } = useNotice();
  const [placement, setPlacement] = useState<AffiliateCommentPlacement | null>(null);
  const [history, setHistory] = useState<AffiliateCommentHistoryResponse>(EMPTY_HISTORY);
  const [cta, setCta] = useState(DEFAULT_CTA);
  const [disclosure, setDisclosure] = useState(DEFAULT_DISCLOSURE);
  const [customMessageTemplate, setCustomMessageTemplate] = useState("");
  const [templates, setTemplates] = useState<AffiliateCommentTemplate[]>([]);
  const [templateId, setTemplateId] = useState<string | undefined>(undefined);
  const [itemTemplateChoiceId, setItemTemplateChoiceId] = useState<string | undefined>(undefined);
  const [sourceMode, setSourceMode] = useState<"SHARED_TEMPLATE" | "ITEM_CUSTOM">("SHARED_TEMPLATE");
  const [attachProductImage, setAttachProductImage] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [creatingAnother, setCreatingAnother] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"preview" | "apply-template" | "approve" | null>(null);
  const [checkingPlacementId, setCheckingPlacementId] = useState<string | null>(null);
  const [verificationJobs, setVerificationJobs] = useState<Record<string, Job>>({});
  const [error, setError] = useState<string | null>(null);

  const activeTemplate = templates.find((candidate) => candidate.is_active) ?? null;
  const selectedTemplate = templates.find((candidate) => candidate.id === templateId) ?? null;
  const selectedItemTemplate = templates.find((candidate) => candidate.id === itemTemplateChoiceId) ?? null;
  const placementTemplate = templates.find((candidate) => candidate.id === placement?.template_id) ?? null;

  async function load() {
    try {
      const [currentPlacement, commentHistory, templateList] = await Promise.all([
        fetchAffiliateCommentPlacement(item.platform_publication_id),
        fetchAffiliateCommentHistory(item.platform_publication_id),
        fetchAffiliateCommentTemplates(),
      ]);
      const configuredTemplate = templateList.templates.find((candidate) => candidate.is_active) ?? null;
      setTemplates(templateList.templates);
      setTemplateId(currentPlacement?.template_id ?? configuredTemplate?.id);
      setItemTemplateChoiceId(configuredTemplate?.id ?? currentPlacement?.template_id ?? undefined);
      const loadedSource = currentPlacement?.metadata_json?.comment_source === "ITEM_CUSTOM" ? "ITEM_CUSTOM" : "SHARED_TEMPLATE";
      setSourceMode(loadedSource);
      setAttachProductImage(
        currentPlacement?.attach_product_image
        ?? configuredTemplate?.attach_product_image
        ?? true,
      );
      if (currentPlacement) {
        setCustomMessageTemplate(String(currentPlacement.metadata_json?.comment_message_template_override ?? currentPlacement.comment_message));
        setCta(
          currentPlacement.template_id
            ? currentPlacement.cta_text
            : configuredTemplate?.default_cta ?? currentPlacement.cta_text,
        );
        setDisclosure(
          currentPlacement.template_id
            ? currentPlacement.disclosure_text
            : configuredTemplate?.default_disclosure ?? currentPlacement.disclosure_text,
        );
      } else if (configuredTemplate) {
        setCta(configuredTemplate.default_cta);
        setDisclosure(configuredTemplate.default_disclosure);
        setCustomMessageTemplate(configuredTemplate.message_template);
      } else {
        setCustomMessageTemplate(DEFAULT_CUSTOM_TEMPLATE);
      }
      setPlacement(currentPlacement);
      setHistory(commentHistory);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateComment.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [item.platform_publication_id]);

  useEffect(() => {
    if (!placement || !["QUEUED", "POSTING"].includes(placement.status)) return;
    const timer = setInterval(() => void load(), 3_000);
    return () => clearInterval(timer);
  }, [placement?.id, placement?.status]);

  useEffect(() => {
    if (!placement?.metadata_json?.previous_posted_placement_id || placement.status !== "DRAFT" || history.can_post_now) return;
    const timer = setInterval(() => void load(), 60_000);
    return () => clearInterval(timer);
  }, [placement?.id, placement?.status, history.can_post_now]);

  useEffect(() => {
    const active = Object.entries(verificationJobs).filter(([, job]) => ["QUEUED", "RUNNING", "RETRYABLE"].includes(job.status));
    if (!active.length) return;
    const timer = setInterval(() => {
      void Promise.all(active.map(async ([placementId, job]) => {
        try {
          const next = await fetchJob(job.id);
          setVerificationJobs((current) => ({ ...current, [placementId]: next }));
          if (["COMPLETED", "FAILED", "CANCELLED"].includes(next.status)) await load();
        } catch {
          // The next manual check can recover from a transient polling failure.
        }
      }));
    }, 2_500);
    return () => clearInterval(timer);
  }, [verificationJobs]);

  async function checkVerification(comment: AffiliateCommentPlacement) {
    setCheckingPlacementId(comment.id);
    setError(null);
    try {
      const response = await verifyAffiliateCommentPlacement(comment.id);
      setVerificationJobs((current) => ({ ...current, [comment.id]: response.job }));
      notify({ message: t(response.reused ? "affiliateComment.verificationJobReused" : "affiliateComment.verificationJobQueued"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateComment.verificationCheckFailed"));
    } finally {
      setCheckingPlacementId(null);
    }
  }

  function selectTemplateVersion(template: AffiliateCommentTemplate) {
    setTemplateId(template.id);
    setCta(template.default_cta);
    setDisclosure(template.default_disclosure);
    setAttachProductImage(template.attach_product_image);
    setConfirmed(false);
  }

  function changeTemplate(templateIdValue: string) {
    const template = templates.find((candidate) => candidate.id === templateIdValue);
    if (template) {
      setSourceMode("SHARED_TEMPLATE");
      selectTemplateVersion(template);
    }
  }

  async function preview(options?: {
    template?: AffiliateCommentTemplate;
    replaceCurrent?: boolean;
    busyKey?: "preview" | "apply-template";
    messageOverride?: string;
    source?: "SHARED_TEMPLATE" | "ITEM_CUSTOM";
    messageTemplateOverride?: string;
  }) {
    const requestedTemplate = options?.template ?? selectedTemplate;
    const replacesPlacementId = !creatingAnother && (options?.replaceCurrent || editing) && placement ? placement.id : undefined;
    const requestedCta = options?.template?.default_cta ?? cta;
    const requestedDisclosure = options?.template?.default_disclosure ?? disclosure;
    const requestedTemplateId = requestedTemplate?.id ?? templateId;
    const requestedSource = options?.source ?? (editing ? sourceMode : "SHARED_TEMPLATE");
    const customTemplateRequestsImage = requestedSource === "ITEM_CUSTOM" && /{{\s*product_image\s*}}/i.test(options?.messageTemplateOverride ?? "");
    const requestedAttachProductImage = customTemplateRequestsImage || (options?.template ? options.template.attach_product_image : attachProductImage);
    setBusy(options?.busyKey ?? "preview");
    setError(null);
    try {
      const response = await previewAffiliateCommentPlacement(item.platform_publication_id, {
        cta_text: requestedCta,
        disclosure_text: requestedDisclosure,
        comment_source: requestedSource,
        ...(requestedSource === "ITEM_CUSTOM" && options?.messageTemplateOverride
          ? { comment_message_template_override: options.messageTemplateOverride }
          : {}),
        ...(options?.messageOverride ? { comment_message_override: options.messageOverride } : {}),
        ...(requestedTemplateId ? { template_id: requestedTemplateId } : {}),
        attach_product_image: requestedAttachProductImage,
        ...(replacesPlacementId ? { replaces_placement_id: replacesPlacementId } : {}),
        ...(creatingAnother && placement ? {
          create_another_comment: true,
          previous_posted_placement_id: placement.id,
        } : {}),
      });
      setPlacement(response.placement);
      setTemplateId(response.placement.template_id ?? requestedTemplateId);
      setItemTemplateChoiceId(response.placement.template_id ?? requestedTemplateId);
      setSourceMode(response.placement.metadata_json?.comment_source === "ITEM_CUSTOM" ? "ITEM_CUSTOM" : "SHARED_TEMPLATE");
      setCustomMessageTemplate(String(response.placement.metadata_json?.comment_message_template_override ?? response.placement.comment_message));
      setCta(response.placement.cta_text);
      setDisclosure(response.placement.disclosure_text);
      setAttachProductImage(response.placement.attach_product_image);
      setConfirmed(false);
      setEditing(false);
      setCreatingAnother(false);
      await load();
      notify({
        message: t(replacesPlacementId ? "affiliateComment.previewRegenerated" : "affiliateComment.previewReady"),
        tone: "success",
      });
    } catch (err) {
      setError(err instanceof Error
        ? err.message
        : t(replacesPlacementId ? "affiliateComment.regenerateError" : "affiliateComment.previewError"));
    } finally {
      setBusy(null);
    }
  }

  function applyTemplateToItem() {
    if (!placement || !selectedItemTemplate || !["DRAFT", "FAILED"].includes(placement.status)) return;
    void preview({ template: selectedItemTemplate, source: "SHARED_TEMPLATE", replaceCurrent: true, busyKey: "apply-template" });
  }

  function beginEdit(sourceOverride?: "SHARED_TEMPLATE" | "ITEM_CUSTOM") {
    if (!placement || !["DRAFT", "FAILED"].includes(placement.status)) return;
    const currentSource = placement.metadata_json?.comment_source === "ITEM_CUSTOM" ? "ITEM_CUSTOM" : "SHARED_TEMPLATE";
    const nextSource = sourceOverride ?? currentSource;
    setTemplateId(placement.template_id ?? activeTemplate?.id);
    setSourceMode(nextSource);
    setCta(placement.cta_text);
    setDisclosure(placement.disclosure_text);
    setCustomMessageTemplate(nextSource === "ITEM_CUSTOM" && currentSource !== "ITEM_CUSTOM"
      ? activeTemplate?.message_template ?? DEFAULT_CUSTOM_TEMPLATE
      : String(placement.metadata_json?.comment_message_template_override ?? placement.comment_message));
    setAttachProductImage(placement.attach_product_image);
    setConfirmed(false);
    setError(null);
    setEditing(true);
  }

  function beginAnotherComment() {
    if (!placement || placement.status !== "POSTED" || !history.can_create_another) return;
    setSourceMode("ITEM_CUSTOM");
    setTemplateId(activeTemplate?.id);
    setCta(activeTemplate?.default_cta ?? DEFAULT_CTA);
    setDisclosure(activeTemplate?.default_disclosure ?? DEFAULT_DISCLOSURE);
    setCustomMessageTemplate("");
    setAttachProductImage(activeTemplate?.attach_product_image ?? true);
    setConfirmed(false);
    setError(null);
    setCreatingAnother(true);
    setEditing(true);
  }

  function cancelEdit() {
    setCta(placement?.cta_text ?? DEFAULT_CTA);
    setDisclosure(placement?.disclosure_text ?? DEFAULT_DISCLOSURE);
    setTemplateId(placement?.template_id ?? activeTemplate?.id);
    setSourceMode(placement?.metadata_json?.comment_source === "ITEM_CUSTOM" ? "ITEM_CUSTOM" : "SHARED_TEMPLATE");
    setAttachProductImage(placement?.attach_product_image ?? activeTemplate?.attach_product_image ?? true);
    setError(null);
    setCreatingAnother(false);
    setEditing(false);
  }

  const templateWasActiveAtPreview = placement?.metadata_json?.template_was_active_at_preview;
  const placementSource = placement?.metadata_json?.comment_source === "ITEM_CUSTOM" ? "ITEM_CUSTOM" : "SHARED_TEMPLATE";
  const isAdditionalPlacement = Boolean(placement?.metadata_json?.previous_posted_placement_id);
  const readinessChecks = placement ? [
    {
      key: "template",
      passed: placementSource === "ITEM_CUSTOM" || (Boolean(placement.template_id) && templateWasActiveAtPreview !== false),
      label: t("affiliateComment.readinessTemplate"),
      detail: placementSource === "ITEM_CUSTOM"
        ? t("affiliateComment.readinessCustomItem")
        : !placement.template_id
        ? t("affiliateComment.readinessTemplateMissing")
        : templateWasActiveAtPreview === false
        ? t("affiliateComment.readinessTemplateTestOnly")
        : t("affiliateComment.readinessTemplateReady").replace("{version}", String(placement.template_version ?? "—")),
    },
    {
      key: "url",
      passed: isPublicHttpsUrl(placement.affiliate_url),
      label: t("affiliateComment.readinessUrl"),
      detail: isPublicHttpsUrl(placement.affiliate_url)
        ? t("affiliateComment.readinessUrlReady")
        : t("affiliateComment.readinessUrlBlocked"),
    },
    {
      key: "content",
      passed: !/{{[^{}]+}}/.test(placement.comment_message),
      label: t("affiliateComment.readinessContent"),
      detail: !/{{[^{}]+}}/.test(placement.comment_message)
        ? t("affiliateComment.readinessContentReady")
        : t("affiliateComment.readinessContentBlocked"),
    },
    {
      key: "image",
      passed: !placement.attach_product_image || Boolean(placement.attachment_image_url),
      label: t("affiliateComment.readinessImage"),
      detail: !placement.attach_product_image
        ? t("affiliateComment.readinessImageDisabled")
        : placement.attachment_image_url
          ? t("affiliateComment.readinessImageReady")
          : t("affiliateComment.readinessImageBlocked"),
    },
    {
      key: "opportunity",
      passed: item.recommendation === "PRIORITY"
        && !item.growth_is_stale
        && item.selected_product_active
        && item.selected_product_availability !== "OUT_OF_STOCK"
        && Boolean(placement.external_reel_id),
      label: t("affiliateComment.readinessOpportunity"),
      detail: item.recommendation === "PRIORITY" && !item.growth_is_stale
        ? t("affiliateComment.readinessOpportunityReady")
        : t("affiliateComment.readinessOpportunityBlocked"),
    },
    ...(isAdditionalPlacement ? [{
      key: "posting-window",
      passed: history.can_post_now,
      label: t("affiliateComment.readinessPostingWindow"),
      detail: history.can_post_now
        ? t("affiliateComment.readinessPostingWindowReady")
        : t(history.blocked_reason === "DAILY_LIMIT"
          ? "affiliateComment.readinessDailyLimit"
          : "affiliateComment.readinessCooldown").replace(
            "{time}",
            history.next_allowed_at ? new Date(history.next_allowed_at).toLocaleString() : "—",
          ),
    }] : []),
  ] : [];
  const readinessReady = readinessChecks.length > 0 && readinessChecks.every((check) => check.passed);
  const itemTemplateNeedsApply = Boolean(
    placement
    && selectedItemTemplate
    && (
      placement.template_id !== selectedItemTemplate.id
      || templateWasActiveAtPreview === false
      || placement.affiliate_url !== item.selected_product_affiliate_url
    ),
  );
  const customMessageHasUnsupportedVariable = [...customMessageTemplate.matchAll(/{{([^{}]+)}}/g)].some((match) => {
    const variable = match[1].trim().toLowerCase();
    return !/^[a-z_][a-z0-9_]*$/.test(variable) || !CUSTOM_TEMPLATE_VARIABLES.has(variable);
  });
  // Existing placements are immutable snapshots. Every replacement draft must
  // validate and render from the product's current catalog URL, not the stale
  // URL captured by the previous placement revision.
  const selectedProductAffiliateUrl = item.selected_product_affiliate_url;
  const selectedProductAffiliateUrlIsPublic = isPublicHttpsUrl(selectedProductAffiliateUrl);
  const customMessageRequestsImage = /{{\s*product_image\s*}}/i.test(customMessageTemplate);
  const customAttachProductImage = attachProductImage || customMessageRequestsImage;
  const customMessageReady = Boolean(customMessageTemplate.trim()) && selectedProductAffiliateUrlIsPublic && !customMessageHasUnsupportedVariable;
  const postedHistory = history.placements.filter((candidate) => candidate.status === "POSTED");

  async function approve() {
    if (!placement || !confirmed || !readinessReady) return;
    setBusy("approve");
    setError(null);
    try {
      const response = await approveAffiliateCommentPlacement(placement.id);
      setPlacement(response.placement);
      notify({ message: t("affiliateComment.approvedQueued"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateComment.approveError"));
    } finally {
      setBusy(null);
    }
  }

  function renderCommentMethodChooser() {
    return <section className="affiliate-comment-method-guide">
      <header>
        <span>1</span>
        <div><strong>{t("affiliateComment.methodStepTitle")}</strong><small>{t("affiliateComment.methodStepHint")}</small></div>
      </header>
      <div className="affiliate-comment-method-options">
        <button aria-pressed={sourceMode === "SHARED_TEMPLATE"} className={sourceMode === "SHARED_TEMPLATE" ? "is-selected" : ""} onClick={() => setSourceMode("SHARED_TEMPLATE")} type="button">
          <i aria-hidden="true">T</i>
          <span><strong>{t("affiliateComment.sharedTemplateMode")}</strong><small>{t("affiliateComment.sharedTemplateBeginnerHint")}</small></span>
          <em>{t(sourceMode === "SHARED_TEMPLATE" ? "affiliateComment.methodSelected" : "affiliateComment.methodRecommended")}</em>
        </button>
        <button aria-pressed={sourceMode === "ITEM_CUSTOM"} className={sourceMode === "ITEM_CUSTOM" ? "is-selected" : ""} onClick={() => setSourceMode("ITEM_CUSTOM")} type="button">
          <i aria-hidden="true">✎</i>
          <span><strong>{t("affiliateComment.customCommentMode")}</strong><small>{t("affiliateComment.customCommentBeginnerHint")}</small></span>
          {sourceMode === "ITEM_CUSTOM" ? <em>{t("affiliateComment.methodSelected")}</em> : null}
        </button>
      </div>
    </section>;
  }

  function renderAffiliateUrlRequirement() {
    if (selectedProductAffiliateUrlIsPublic) return null;
    return <div className="affiliate-comment-url-requirement is-blocked" id="affiliate-comment-url-blocker" role="alert">
      <i aria-hidden="true">!</i>
      <div>
        <strong>{t("affiliateComment.affiliateUrlBlockedTitle")}</strong>
        <small>{t("affiliateComment.affiliateUrlBlockedHint")}</small>
        <code>{selectedProductAffiliateUrl || t("affiliateComment.affiliateUrlMissing")}</code>
      </div>
      <a href={`/publishing/settings/affiliate-catalog?edit_product_id=${encodeURIComponent(item.selected_product_id)}&focus=affiliate_url`}>{t("affiliateComment.fixAffiliateUrl")}</a>
    </div>;
  }

  if (loading) return <p className="muted affiliate-comment-loading">{t("affiliateComment.loading")}</p>;

  return <section className="affiliate-comment-panel">
    <header>
      <div>
        <span>{t("affiliateComment.eyebrow")}</span>
        <strong>{t("affiliateComment.title")}</strong>
        <small>{t("affiliateComment.hint")}</small>
      </div>
      {placement ? <span className={`affiliate-comment-status is-${placement.status.toLowerCase()}`}>{t(`affiliateComment.statusValue.${placement.status}`)}</span> : null}
    </header>

    {error ? <div className="inline-error" role="alert">{error}</div> : null}

    {item.recommendation !== "PRIORITY" ? <div className="affiliate-comment-blocked">
      <strong>{t("affiliateComment.priorityRequired")}</strong>
      <small>{t("affiliateComment.priorityRequiredHint")}</small>
    </div> : placement && !editing ? <>
      <section className="affiliate-comment-preview">
        <header>
          <div>
            <strong>{t("affiliateComment.previewTitle")}</strong>
            <small>{t("affiliateComment.previewLocked")}</small>
          </div>
          <span className={`affiliate-comment-template-badge ${placementSource === "ITEM_CUSTOM" ? "is-custom" : templateWasActiveAtPreview === false ? "is-test" : "is-active"}`}>
            {t(placementSource === "ITEM_CUSTOM" ? "affiliateComment.customCommentMode" : templateWasActiveAtPreview === false ? "affiliateComment.templateTestOnly" : "affiliateComment.templateApproved")}
          </span>
        </header>
        {placement.attachment_image_url ? <div className="affiliate-comment-attachment">
          <img alt={item.selected_product_name} src={affiliateImagePreviewUrl(placement.attachment_image_url)} />
          <div><strong>{t("affiliateComment.attachmentImage")}</strong><small>{t("affiliateComment.imageSnapshotLocked")}</small></div>
        </div> : <div className="affiliate-comment-no-attachment">
          <strong>{t("affiliateComment.noImage")}</strong>
          <small>{t("affiliateComment.noImageHint")}</small>
        </div>}
        <pre>{placement.comment_message}</pre>
        <dl>
          <div><dt>{t("affiliateComment.page")}</dt><dd>{item.page_display_name}</dd></div>
          <div><dt>{t("affiliateComment.reel")}</dt><dd>{placement.external_reel_id}</dd></div>
          <div><dt>{t("affiliateComment.product")}</dt><dd>{item.selected_product_name}</dd></div>
          <div><dt>{t("affiliateComment.commentSource")}</dt><dd>{placementSource === "ITEM_CUSTOM" ? t("affiliateComment.customCommentMode") : `${placementTemplate?.name ?? String(placement.metadata_json?.template_name ?? "—")} · v${placement.template_version ?? "—"}`}</dd></div>
          <div><dt>{t("affiliateComment.gates")}</dt><dd>Growth {Math.round(item.growth_assessment?.growth_score ?? 0)} · Fit {Math.round(item.affiliate_fit_score ?? 0)}</dd></div>
        </dl>
      </section>

      {postedHistory.length ? <details className="affiliate-comment-history">
        <summary><span>{t("affiliateComment.historyTitle")}</span><em>{t("affiliateComment.historyQuota").replace("{count}", String(history.posted_count_24h)).replace("{max}", String(history.max_posts_per_24h))}</em></summary>
        <div>{postedHistory.map((comment, index) => <article key={comment.id}>
          <header><strong>{t("affiliateComment.historyItem").replace("{number}", String(postedHistory.length - index))}</strong><small>{comment.posted_at ? new Date(comment.posted_at).toLocaleString() : "—"}</small></header>
          {(() => {
            const verification = commentVerification(comment);
            const job = verificationJobs[comment.id];
            const jobActive = Boolean(job && ["QUEUED", "RUNNING", "RETRYABLE"].includes(job.status));
            const displayStatus = jobActive ? "PENDING" : verification.status;
            return <section className="affiliate-comment-verification-summary">
              <div className="affiliate-comment-verification-heading">
                <span className={`affiliate-comment-verification-badge is-${displayStatus.toLowerCase().replace("_", "-")}`}>{t(`affiliateComment.verificationStatus.${displayStatus}`)}</span>
                <small>{verification.checked_at ? t("affiliateComment.lastChecked").replace("{time}", new Date(verification.checked_at).toLocaleString()) : t("affiliateComment.notCheckedHint")}</small>
              </div>
              <div><span>{t("affiliateComment.facebookCommentCheck")}</span><strong>{verification.comment?.status ? t(`affiliateComment.commentCheckStatus.${verification.comment.status}`) : "—"}</strong></div>
              {comment.attach_product_image ? <div><span>{t("affiliateComment.imageAttachmentCheck")}</span><strong>{verification.comment?.attachment_status ? t(`affiliateComment.attachmentCheckStatus.${verification.comment.attachment_status}`) : "—"}</strong></div> : null}
              <div><span>{t("affiliateComment.affiliateLinkCheck")}</span><strong>{verification.link?.status ? t(`affiliateComment.linkCheckStatus.${verification.link.status}`) : "—"}</strong></div>
            </section>;
          })()}
          <p>{comment.comment_message}</p>
          <footer><span>{comment.metadata_json?.comment_source === "ITEM_CUSTOM" ? t("affiliateComment.customCommentMode") : t("affiliateComment.sharedTemplateMode")}</span><div>{comment.external_comment_permalink ? <a href={comment.external_comment_permalink} rel="noreferrer" target="_blank">{t("affiliateComment.openComment")}</a> : null}<AsyncButton pending={checkingPlacementId === comment.id || Boolean(verificationJobs[comment.id] && ["QUEUED", "RUNNING", "RETRYABLE"].includes(verificationJobs[comment.id].status))} onClick={() => void checkVerification(comment)}>{t("affiliateComment.checkNow")}</AsyncButton></div></footer>
        </article>)}</div>
      </details> : null}

      {["DRAFT", "FAILED"].includes(placement.status) ? <section className="affiliate-comment-item-template">
        {renderCommentMethodChooser()}
        {sourceMode === "SHARED_TEMPLATE" ? <section className="affiliate-comment-method-config">
          <header><span>2</span><div><strong>{t("affiliateComment.chooseTemplateStepTitle")}</strong><small>{t("affiliateComment.chooseTemplateStepHint")}</small></div><a href="/publishing/settings/affiliate-comments">{t("affiliateComment.editGlobalTemplates")}</a></header>
          <div className="affiliate-comment-item-template-controls">
            <label><span>{t("affiliateComment.currentItemTemplate")}</span><select disabled={templates.length === 0} onChange={(event) => setItemTemplateChoiceId(event.target.value)} value={itemTemplateChoiceId ?? ""}><option disabled value="">{t("affiliateComment.selectTemplate")}</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name} · v{template.version} · {t(template.is_active ? "affiliateComment.templateDefault" : "affiliateComment.templateTestOnly")}</option>)}</select></label>
            {selectedItemTemplate ? <span className={`affiliate-comment-template-badge ${selectedItemTemplate.is_active ? "is-active" : "is-test"}`}>{t(selectedItemTemplate.is_active ? "affiliateComment.templateDefault" : "affiliateComment.templateTestOnly")}</span> : null}
            <AsyncButton disabled={!itemTemplateNeedsApply || !selectedProductAffiliateUrlIsPublic} pending={busy === "apply-template"} statusId={!selectedProductAffiliateUrlIsPublic ? "affiliate-comment-url-blocker" : undefined} onClick={applyTemplateToItem}>{t("affiliateComment.useSelectedTemplate")}</AsyncButton>
          </div>
          <small>{selectedItemTemplate ? t(selectedItemTemplate.is_active ? "affiliateComment.itemTemplateActiveHint" : "affiliateComment.itemTemplateTestHint") : t("affiliateComment.noTemplateHint")}</small>
          {renderAffiliateUrlRequirement()}
        </section> : <section className="affiliate-comment-method-config">
          <header><span>2</span><div><strong>{t("affiliateComment.writeCustomStepTitle")}</strong><small>{t("affiliateComment.writeCustomStepHint")}</small></div></header>
          <button className="affiliate-comment-start-custom" onClick={() => beginEdit("ITEM_CUSTOM")} type="button">{t("affiliateComment.startWritingComment")}</button>
        </section>}
      </section> : null}

      {["DRAFT", "FAILED"].includes(placement.status) ? <section className={`affiliate-comment-readiness ${readinessReady ? "is-ready" : "needs-attention"}`}>
        <header>
          <div><strong>{t("affiliateComment.readinessTitle")}</strong><small>{t("affiliateComment.readinessHint")}</small></div>
          <span>{t(readinessReady ? "affiliateComment.readinessReady" : "affiliateComment.readinessBlocked")}</span>
        </header>
        <ul>{readinessChecks.map((check) => <li className={check.passed ? "is-pass" : "is-blocked"} key={check.key}>
          <i aria-hidden="true">{check.passed ? "✓" : "!"}</i>
          <span><strong>{check.label}</strong><small>{check.detail}</small></span>
        </li>)}</ul>
      </section> : null}

      {placement.error_message ? <div className="affiliate-comment-failure">
        <strong>{placement.error_code || t("affiliateComment.failed")}</strong>
        <small>{placement.error_message}</small>
      </div> : null}

      {placement.status === "DRAFT" || placement.status === "FAILED" ? <footer>
        <label>
          <input checked={confirmed} disabled={!readinessReady} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />
          <span>{readinessReady ? t("affiliateComment.confirmPost") : t("affiliateComment.resolveReadinessFirst")}</span>
        </label>
        <div className="affiliate-comment-footer-actions">
          <button className="affiliate-comment-edit-button" onClick={() => beginEdit("ITEM_CUSTOM")} type="button">{t("affiliateComment.customizePreview")}</button>
          <AsyncButton className="primary" disabled={!confirmed || !readinessReady} pending={busy === "approve"} onClick={() => void approve()}>{t("affiliateComment.approvePost")}</AsyncButton>
        </div>
      </footer> : placement.status === "POSTED" ? <footer className="is-posted">
        <div><strong>{t("affiliateComment.posted")}</strong><small>{t("affiliateComment.externalId").replace("{id}", placement.external_comment_id || "—")}</small><small>{history.blocked_reason === "DAILY_LIMIT" ? t("affiliateComment.anotherDailyLimit").replace("{time}", history.next_allowed_at ? new Date(history.next_allowed_at).toLocaleString() : "—") : history.blocked_reason === "COOLDOWN" ? t("affiliateComment.anotherCooldownHint").replace("{time}", history.next_allowed_at ? new Date(history.next_allowed_at).toLocaleString() : "—") : t("affiliateComment.anotherReadyHint")}</small></div>
        <div className="affiliate-comment-posted-actions">
          {placement.external_comment_permalink ? <a href={placement.external_comment_permalink} rel="noreferrer" target="_blank">{t("affiliateComment.openComment")}</a> : null}
          <button disabled={!history.can_create_another} onClick={beginAnotherComment} type="button">{t("affiliateComment.createAnother")}</button>
        </div>
      </footer> : <div className="affiliate-comment-progress">
        <i aria-hidden="true" />
        <div><strong>{t(`affiliateComment.statusValue.${placement.status}`)}</strong><small>{t("affiliateComment.keepOpen")}</small></div>
      </div>}
    </> : editing && placement ? <>
      {creatingAnother ? <section className="affiliate-comment-another-note"><strong>{t("affiliateComment.anotherDraftTitle").replace("{number}", String(postedHistory.length + 1))}</strong><small>{t("affiliateComment.anotherDraftHint")}</small></section> : null}
      {renderCommentMethodChooser()}
      {sourceMode === "SHARED_TEMPLATE" ? <section className="affiliate-comment-method-config">
        <header><span>2</span><div><strong>{t("affiliateComment.chooseTemplateStepTitle")}</strong><small>{t("affiliateComment.chooseTemplateStepHint")}</small></div><a href="/publishing/settings/affiliate-comments">{t("affiliateComment.editGlobalTemplates")}</a></header>
        <section className="affiliate-comment-template-picker">
          <label>
            <span>{t("affiliateComment.savedTemplate")}</span>
            <select disabled={templates.length === 0} onChange={(event) => changeTemplate(event.target.value)} value={templateId ?? ""}>
              <option disabled value="">{t("affiliateComment.selectTemplate")}</option>
              {templates.map((template) => <option key={template.id} value={template.id}>{template.name} · v{template.version} · {t(template.is_active ? "affiliateComment.templateDefault" : "affiliateComment.templateTestOnly")}</option>)}
            </select>
          </label>
          {selectedTemplate ? <div><span className={`affiliate-comment-template-badge ${selectedTemplate.is_active ? "is-active" : "is-test"}`}>{t(selectedTemplate.is_active ? "affiliateComment.templateDefault" : "affiliateComment.templateTestOnly")}</span><small>{t(selectedTemplate.is_active ? "affiliateComment.templateBeginnerReadyHint" : "affiliateComment.templateTestOnlyBeginnerHint")}</small></div> : null}
        </section>
        {renderAffiliateUrlRequirement()}
        <footer className="affiliate-comment-step-action">
          <div><span>3</span><small>{t("affiliateComment.draftStepHint")}</small></div>
          <div className="affiliate-comment-footer-actions">
            <button className="affiliate-comment-edit-button" disabled={busy === "preview"} onClick={cancelEdit} type="button">{t("affiliateComment.cancelEdit")}</button>
            <AsyncButton className="primary" disabled={!templateId || !selectedProductAffiliateUrlIsPublic} pending={busy === "preview"} statusId={!selectedProductAffiliateUrlIsPublic ? "affiliate-comment-url-blocker" : undefined} onClick={() => void preview({ source: "SHARED_TEMPLATE" })}>{t("affiliateComment.createDraftFromTemplate")}</AsyncButton>
          </div>
        </footer>
      </section> : <section className="affiliate-comment-method-config">
        <header><span>2</span><div><strong>{t("affiliateComment.writeCustomStepTitle")}</strong><small>{t("affiliateComment.writeCustomStepHint")}</small></div></header>
        <label className="affiliate-comment-message-editor">
          <span>{t("affiliateComment.commentContent")}</span>
          <textarea maxLength={5000} onChange={(event) => setCustomMessageTemplate(event.target.value)} rows={10} value={customMessageTemplate} />
        </label>
        <section className="affiliate-comment-variable-list">
          <strong>{t("affiliateComment.availableVariables")}</strong>
          <div>{[...CUSTOM_TEMPLATE_VARIABLES].map((variable) => <code key={variable}>{`{{${variable}}}`}</code>)}</div>
          <small>{t("affiliateComment.customVariablesHint")}</small>
        </section>
        <div className={`affiliate-comment-message-rule ${customMessageReady ? "is-ready" : "is-blocked"} ${!selectedProductAffiliateUrlIsPublic ? "is-hidden-by-url-blocker" : ""}`}>
          <i aria-hidden="true">{customMessageReady ? "✓" : "!"}</i>
          <span>{t(customMessageHasUnsupportedVariable
            ? "affiliateComment.customMessageVariableBlocked"
            : !selectedProductAffiliateUrlIsPublic
                ? "affiliateComment.customMessageUrlInvalid"
                : "affiliateComment.customMessageReady")}</span>
        </div>
        {renderAffiliateUrlRequirement()}
        <div className="affiliate-comment-locked-url">
          <span>{t("affiliateComment.extractedAffiliateUrl")}</span>
          <code>{selectedProductAffiliateUrl}</code>
          <small>{t("affiliateComment.extractedAffiliateUrlHint")} <a href="/publishing/settings/affiliate-catalog">{t("affiliateComment.manageProductUrl")}</a></small>
        </div>
        <label className="affiliate-comment-image-toggle"><input checked={customAttachProductImage} disabled={customMessageRequestsImage} onChange={(event) => setAttachProductImage(event.target.checked)} type="checkbox" /><span>{t(customMessageRequestsImage ? "affiliateComment.imageForcedByVariable" : "affiliateComment.attachImageForCustom")}</span></label>
        <div className={`affiliate-comment-attachment-source ${customAttachProductImage && item.selected_product_image_url ? "has-image" : "is-empty"}`}>
          {customAttachProductImage && item.selected_product_image_url ? <img alt={item.selected_product_name} src={affiliateImagePreviewUrl(item.selected_product_image_url)} /> : <span>{customAttachProductImage ? "IMG" : "TXT"}</span>}
          <div><strong>{!customAttachProductImage ? t("affiliateComment.textOnlyTemplate") : item.selected_product_image_url ? t("affiliateComment.extractedProductImage") : t("affiliateComment.noImage")}</strong><small>{!customAttachProductImage ? t("affiliateComment.textOnlyTemplateHint") : item.selected_product_image_url ? t("affiliateComment.extractedProductImageHint") : t("affiliateComment.noImageHint")}</small></div>
        </div>
        <footer className="affiliate-comment-step-action">
          <div><span>3</span><small>{t("affiliateComment.draftStepHint")}</small></div>
          <div className="affiliate-comment-footer-actions">
            <button className="affiliate-comment-edit-button" disabled={busy === "preview"} onClick={cancelEdit} type="button">{t("affiliateComment.cancelEdit")}</button>
            <AsyncButton className="primary" disabled={!customMessageReady || (customAttachProductImage && !item.selected_product_image_url)} pending={busy === "preview"} statusId={!selectedProductAffiliateUrlIsPublic ? "affiliate-comment-url-blocker" : undefined} onClick={() => void preview({ source: "ITEM_CUSTOM", messageTemplateOverride: customMessageTemplate })}>{t(creatingAnother ? "affiliateComment.createCustomDraft" : "affiliateComment.updateCustomDraft")}</AsyncButton>
          </div>
        </footer>
      </section>}
    </> : <>
      {renderCommentMethodChooser()}
      {sourceMode === "SHARED_TEMPLATE" ? <section className="affiliate-comment-method-config">
        <header><span>2</span><div><strong>{t("affiliateComment.chooseTemplateStepTitle")}</strong><small>{t("affiliateComment.chooseTemplateStepHint")}</small></div><a href="/publishing/settings/affiliate-comments">{t("affiliateComment.editGlobalTemplates")}</a></header>
        <section className="affiliate-comment-template-picker">
          <label><span>{t("affiliateComment.savedTemplate")}</span><select disabled={templates.length === 0} onChange={(event) => changeTemplate(event.target.value)} value={templateId ?? ""}><option disabled value="">{t("affiliateComment.selectTemplate")}</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name} · v{template.version} · {t(template.is_active ? "affiliateComment.templateDefault" : "affiliateComment.templateTestOnly")}</option>)}</select></label>
          {selectedTemplate ? <div><span className={`affiliate-comment-template-badge ${selectedTemplate.is_active ? "is-active" : "is-test"}`}>{t(selectedTemplate.is_active ? "affiliateComment.templateDefault" : "affiliateComment.templateTestOnly")}</span><small>{t(selectedTemplate.is_active ? "affiliateComment.templateBeginnerReadyHint" : "affiliateComment.templateTestOnlyBeginnerHint")}</small></div> : <div><small>{t("affiliateComment.noTemplateHint")} <a href="/publishing/settings/affiliate-comments">{t("affiliateComment.manageTemplates")}</a></small></div>}
        </section>
        {renderAffiliateUrlRequirement()}
        <div className={`affiliate-comment-attachment-source ${attachProductImage && item.selected_product_image_url ? "has-image" : "is-empty"}`}>
          {attachProductImage && item.selected_product_image_url ? <img alt={item.selected_product_name} src={affiliateImagePreviewUrl(item.selected_product_image_url)} /> : <span>{attachProductImage ? "IMG" : "TXT"}</span>}
          <div><strong>{!attachProductImage ? t("affiliateComment.textOnlyTemplate") : item.selected_product_image_url ? t("affiliateComment.imageWillAttach") : t("affiliateComment.noImage")}</strong><small>{!attachProductImage ? t("affiliateComment.textOnlyTemplateHint") : item.selected_product_image_url ? t("affiliateComment.publicImageRequired") : t("affiliateComment.noImageHint")}</small></div>
        </div>
        <footer className="affiliate-comment-step-action"><div><span>3</span><small>{t("affiliateComment.draftStepHint")}</small></div><div className="affiliate-comment-footer-actions"><AsyncButton className="primary" disabled={!templateId || !selectedProductAffiliateUrlIsPublic} pending={busy === "preview"} statusId={!selectedProductAffiliateUrlIsPublic ? "affiliate-comment-url-blocker" : undefined} onClick={() => void preview({ source: "SHARED_TEMPLATE" })}>{t("affiliateComment.createDraftFromTemplate")}</AsyncButton></div></footer>
      </section> : <section className="affiliate-comment-method-config">
        <header><span>2</span><div><strong>{t("affiliateComment.writeCustomStepTitle")}</strong><small>{t("affiliateComment.writeCustomStepHint")}</small></div></header>
        <label className="affiliate-comment-message-editor"><span>{t("affiliateComment.commentContent")}</span><textarea maxLength={5000} onChange={(event) => setCustomMessageTemplate(event.target.value)} rows={10} value={customMessageTemplate} /></label>
        <section className="affiliate-comment-variable-list"><strong>{t("affiliateComment.availableVariables")}</strong><div>{[...CUSTOM_TEMPLATE_VARIABLES].map((variable) => <code key={variable}>{`{{${variable}}}`}</code>)}</div><small>{t("affiliateComment.customVariablesHint")}</small></section>
        <div className={`affiliate-comment-message-rule ${customMessageReady ? "is-ready" : "is-blocked"} ${!selectedProductAffiliateUrlIsPublic ? "is-hidden-by-url-blocker" : ""}`}><i aria-hidden="true">{customMessageReady ? "✓" : "!"}</i><span>{t(customMessageHasUnsupportedVariable ? "affiliateComment.customMessageVariableBlocked" : !selectedProductAffiliateUrlIsPublic ? "affiliateComment.customMessageUrlInvalid" : "affiliateComment.customMessageReady")}</span></div>
        {renderAffiliateUrlRequirement()}
        <div className="affiliate-comment-locked-url"><span>{t("affiliateComment.extractedAffiliateUrl")}</span><code>{item.selected_product_affiliate_url}</code><small>{t("affiliateComment.extractedAffiliateUrlHint")} <a href="/publishing/settings/affiliate-catalog">{t("affiliateComment.manageProductUrl")}</a></small></div>
        <label className="affiliate-comment-image-toggle"><input checked={customAttachProductImage} disabled={customMessageRequestsImage} onChange={(event) => setAttachProductImage(event.target.checked)} type="checkbox" /><span>{t(customMessageRequestsImage ? "affiliateComment.imageForcedByVariable" : "affiliateComment.attachImageForCustom")}</span></label>
        <div className={`affiliate-comment-attachment-source ${customAttachProductImage && item.selected_product_image_url ? "has-image" : "is-empty"}`}>{customAttachProductImage && item.selected_product_image_url ? <img alt={item.selected_product_name} src={affiliateImagePreviewUrl(item.selected_product_image_url)} /> : <span>{customAttachProductImage ? "IMG" : "TXT"}</span>}<div><strong>{!customAttachProductImage ? t("affiliateComment.textOnlyTemplate") : item.selected_product_image_url ? t("affiliateComment.extractedProductImage") : t("affiliateComment.noImage")}</strong><small>{!customAttachProductImage ? t("affiliateComment.textOnlyTemplateHint") : item.selected_product_image_url ? t("affiliateComment.extractedProductImageHint") : t("affiliateComment.noImageHint")}</small></div></div>
        <footer className="affiliate-comment-step-action"><div><span>3</span><small>{t("affiliateComment.draftStepHint")}</small></div><div className="affiliate-comment-footer-actions"><AsyncButton className="primary" disabled={!customMessageReady || (customAttachProductImage && !item.selected_product_image_url)} pending={busy === "preview"} statusId={!selectedProductAffiliateUrlIsPublic ? "affiliate-comment-url-blocker" : undefined} onClick={() => void preview({ source: "ITEM_CUSTOM", messageTemplateOverride: customMessageTemplate })}>{t("affiliateComment.createCustomDraft")}</AsyncButton></div></footer>
      </section>}
    </>}
  </section>;
}
