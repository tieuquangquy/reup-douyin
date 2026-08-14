"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import {
  bulkImportAffiliateProducts,
  createAffiliateProduct,
  fetchAffiliateProducts,
  fetchContentTopics,
  uploadAffiliateProductImage,
  updateAffiliateProduct,
} from "../../lib/api";
import { parseAffiliateCatalogCsv } from "../../lib/affiliateCatalogCsv";
import { affiliateImagePreviewUrl } from "../../lib/affiliateImagePresentation";
import { useT } from "../../lib/i18n";
import { isPublicHttpsUrl } from "../../lib/publicHttpsUrl";
import type { AffiliateAvailability, AffiliatePlatform, AffiliateProduct, AffiliateProductInput } from "../../types/affiliate";
import type { TopicCategory } from "../../types/content-intelligence";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { formatDateTime } from "../ops-console/OpsShared";
import { IntelligenceCatalogWorksheetSkeleton } from "./IntelligenceDataSkeleton";
import { PublishingSettingsNav } from "./PublishingSettingsNav";

type AffiliateProductDraft = Omit<AffiliateProductInput, "topic_ids"> & {
  /** The editor always owns an explicit selection, even for a new product. */
  topic_ids: string[];
};

const EMPTY_DRAFT: AffiliateProductDraft = {
  platform: "SHOPEE",
  external_product_id: null,
  merchant_name: null,
  name: "",
  description: null,
  image_url: null,
  product_url: null,
  affiliate_url: "",
  currency_code: "VND",
  price_amount: null,
  commission_rate_percent: null,
  commission_amount: null,
  availability_status: "UNKNOWN",
  keywords: [],
  supported_platforms: ["FACEBOOK_REELS"],
  topic_ids: [],
  is_active: true,
};

const CSV_HEADER = "platform,external_product_id,merchant_name,name,description,image_url,product_url,affiliate_url,currency_code,price_amount,commission_rate_percent,availability_status,keywords,supported_platforms,topic_codes,is_active";

const PLATFORM_LABEL: Record<AffiliatePlatform, string> = {
  SHOPEE: "Shopee",
  TIKTOK_SHOP: "TikTok Shop",
  FACEBOOK: "Facebook",
  OTHER: "Other",
};

type CatalogGlyphKind = "refresh" | "plus" | "import" | "edit" | "power" | "close" | "check" | "image" | "link";


function CatalogGlyph({ kind }: { kind: CatalogGlyphKind }) {
  const common = {
    "aria-hidden": true as const,
    className: "affiliate-catalog-toolbar__glyph",
    fill: "none",
    viewBox: "0 0 24 24",
  };
  if (kind === "plus") {
    return (
      <svg {...common}>
        <path d="M12 6.5v11M6.5 12h11" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "import") {
    return (
      <svg {...common}>
        <path d="M7 4.8h7.2L17.2 8v11.2H7V4.8z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.85" />
        <path d="M14 4.8V8h3.2M9.4 13.2h5.2M9.4 16.2h3.6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "edit") {
    return (
      <svg {...common}>
        <path d="M5 16.6h3.2L16.4 8.4a1.4 1.4 0 0 0 0-2L15 4.9a1.4 1.4 0 0 0-2 0L5 13.4v3.2z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.85" />
        <path d="m12.2 6.2 3.1 3.1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "power") {
    return (
      <svg {...common}>
        <path d="M12 6.5v5.2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.85" />
        <path d="M8.1 8.4a5.2 5.2 0 1 0 7.8 0" stroke="currentColor" strokeLinecap="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "close") {
    return (
      <svg {...common}>
        <path d="m7.5 7.5 9 9M16.5 7.5l-9 9" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "check") {
    return (
      <svg {...common}>
        <path d="m6.8 12.2 3.2 3.2 7.2-7.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "image") {
    return (
      <svg {...common}>
        <rect height="12" rx="2" stroke="currentColor" strokeWidth="1.85" width="14" x="5" y="6" />
        <circle cx="9.2" cy="10.2" fill="currentColor" r="1.25" />
        <path d="m8.2 16.2 3.1-3.4 2.2 2.4 2.3-2.8 3.2 3.8" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "link") {
    return (
      <svg {...common}>
        <path d="M10 8H8.2A2.2 2.2 0 0 0 6 10.2v5.6A2.2 2.2 0 0 0 8.2 18h5.6A2.2 2.2 0 0 0 16 15.8V14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
        <path d="M13 6h5v5M18 6l-6.5 6.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M19.2 8.2V12h-3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M4.8 15.8V12h3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M7.05 9.15a6.2 6.2 0 0 1 10.4-1.75L19.2 9.15M4.8 14.85l1.75 1.75a6.2 6.2 0 0 0 10.4-1.75" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
    </svg>
  );
}


function draftValueChanged(previous: unknown, next: unknown): boolean {
  return JSON.stringify(previous ?? null) !== JSON.stringify(next ?? null);
}


export function AffiliateCatalogPage() {
  const t = useT();
  const { notify } = useNotice();
  const [products, setProducts] = useState<AffiliateProduct[]>([]);
  const [topics, setTopics] = useState<TopicCategory[]>([]);
  const [total, setTotal] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const [outOfStockCount, setOutOfStockCount] = useState(0);
  const [draft, setDraft] = useState<AffiliateProductDraft>(EMPTY_DRAFT);
  const [editingProductId, setEditingProductId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [csvText, setCsvText] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deepLink, setDeepLink] = useState({ productId: "", focus: "" });
  const pendingImageUrlRef = useRef<string | null>(null);
  const originalDraftRef = useRef<AffiliateProductDraft | null>(null);
  const affiliateUrlInputRef = useRef<HTMLInputElement | null>(null);
  const deepLinkHandledRef = useRef(false);

  async function load(showNotice = false) {
    setLoading(true);
    setError(null);
    try {
      const [catalog, taxonomy] = await Promise.all([
        fetchAffiliateProducts({ query: query || undefined, limit: 200 }),
        fetchContentTopics(),
      ]);
      setProducts(catalog.products);
      setTotal(catalog.total);
      setActiveCount(catalog.active_count);
      setOutOfStockCount(catalog.out_of_stock_count);
      setTopics(taxonomy.topics);
      if (showNotice) notify({ message: t("affiliateCatalog.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCatalog.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [query]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setDeepLink({
      productId: params.get("edit_product_id") ?? "",
      focus: params.get("focus") ?? "",
    });
  }, []);

  useEffect(() => {
    if (loading || deepLinkHandledRef.current) return;
    const productId = deepLink.productId;
    if (!productId) return;
    deepLinkHandledRef.current = true;
    const product = products.find((candidate) => candidate.id === productId);
    if (product) openEditForm(product);
  }, [deepLink.productId, loading, products]);

  useEffect(() => {
    if (showForm && editingProductId && deepLink.focus === "affiliate_url") {
      affiliateUrlInputRef.current?.focus();
      affiliateUrlInputRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [deepLink.focus, showForm, editingProductId]);

  const topicByCode = useMemo(() => new Map(topics.map((topic) => [topic.code, topic])), [topics]);
  const coldLoading = loading && products.length === 0 && !error;

  function patchDraft(patch: Partial<AffiliateProductDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function openCreateForm() {
    if (showForm && !editingProductId) {
      closeProductForm();
      return;
    }
    pendingImageUrlRef.current = null;
    originalDraftRef.current = null;
    setEditingProductId(null);
    setDraft({ ...EMPTY_DRAFT });
    setShowImport(false);
    setShowForm(true);
  }

  function openEditForm(product: AffiliateProduct) {
    pendingImageUrlRef.current = null;
    setEditingProductId(product.id);
    const nextDraft: AffiliateProductDraft = {
      platform: product.platform,
      external_product_id: product.external_product_id,
      merchant_name: product.merchant_name,
      name: product.name,
      description: product.description,
      image_url: product.image_url,
      product_url: product.product_url,
      affiliate_url: product.affiliate_url,
      currency_code: product.currency_code,
      price_amount: product.price_amount,
      commission_rate_percent: product.commission_rate_percent,
      commission_amount: product.commission_amount,
      availability_status: product.availability_status,
      keywords: product.keywords,
      supported_platforms: product.supported_platforms,
      topic_ids: product.topic_ids,
      is_active: product.is_active,
    };
    originalDraftRef.current = nextDraft;
    setDraft(nextDraft);
    setShowImport(false);
    setShowForm(true);
  }

  function closeProductForm() {
    pendingImageUrlRef.current = null;
    originalDraftRef.current = null;
    setEditingProductId(null);
    setDraft({ ...EMPTY_DRAFT });
    setShowForm(false);
  }

  async function saveProduct() {
    if (!draft.name.trim() || !isPublicHttpsUrl(draft.affiliate_url)) return;
    const productId = editingProductId;
    setBusy(productId ? `update-${productId}` : "create");
    setError(null);
    try {
      const nextDraft: AffiliateProductInput = {
        ...draft,
        image_url: pendingImageUrlRef.current ?? draft.image_url,
        name: draft.name.trim(),
        affiliate_url: draft.affiliate_url.trim(),
      };
      let persisted: AffiliateProduct;
      if (productId) {
        const original = originalDraftRef.current;
        const changedPayload = Object.fromEntries(
          Object.entries(nextDraft).filter(([key, value]) => (
            original == null || draftValueChanged(original[key as keyof AffiliateProductInput], value)
          )),
        ) as Partial<AffiliateProductInput>;
        persisted = Object.keys(changedPayload).length
          ? await updateAffiliateProduct(productId, changedPayload)
          : products.find((product) => product.id === productId) ?? await updateAffiliateProduct(productId, {});
      } else {
        persisted = await createAffiliateProduct(nextDraft);
      }
      if ((persisted.image_url ?? null) !== (nextDraft.image_url ?? null)) {
        throw new Error(t("affiliateCatalog.imagePersistError"));
      }
      setProducts((current) => {
        const exists = current.some((product) => product.id === persisted.id);
        return exists
          ? current.map((product) => product.id === persisted.id ? persisted : product)
          : [persisted, ...current];
      });
      closeProductForm();
      await load();
      notify({ message: t(productId ? "affiliateCatalog.updated" : "affiliateCatalog.created"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t(productId ? "affiliateCatalog.updateError" : "affiliateCatalog.createError"));
    } finally {
      setBusy(null);
    }
  }

  async function importCsv() {
    const parsed = parseAffiliateCatalogCsv(csvText);
    if (!parsed.length) return;
    const unknownTopicCodes = [...new Set(parsed.flatMap((row) => row.topic_codes).filter((code) => !topicByCode.has(code)))];
    if (unknownTopicCodes.length) {
      setError(t("affiliateCatalog.unknownTopics").replace("{codes}", unknownTopicCodes.join(", ")));
      return;
    }
    setBusy("import");
    setError(null);
    try {
      const products = parsed.map(({ topic_codes, ...product }) => ({
        ...product,
        topic_ids: topic_codes.map((code) => topicByCode.get(code)?.id).filter((id): id is string => Boolean(id)),
      }));
      const result = await bulkImportAffiliateProducts(products);
      setCsvText("");
      setShowImport(false);
      await load();
      notify({ message: t("affiliateCatalog.imported").replace("{created}", String(result.created_count)).replace("{updated}", String(result.updated_count)), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCatalog.importError"));
    } finally {
      setBusy(null);
    }
  }

  async function ingestCatalogImage(file: File, input?: HTMLInputElement) {
    if (file.size > 8 * 1024 * 1024) {
      setError(t("affiliateCatalog.imageTooLarge"));
      if (input) input.value = "";
      return;
    }
    if (!(["image/jpeg", "image/png", "image/webp"] as string[]).includes(file.type.toLowerCase())) {
      setError(t("affiliateCatalog.imageUploadError"));
      if (input) input.value = "";
      return;
    }
    setBusy("image-upload");
    setError(null);
    try {
      const uploaded = await uploadAffiliateProductImage(file);
      pendingImageUrlRef.current = uploaded.image_url;
      patchDraft({ image_url: uploaded.image_url });
      notify({ message: t("affiliateCatalog.imageUploaded"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCatalog.imageUploadError"));
    } finally {
      setBusy(null);
      if (input) input.value = "";
    }
  }

  async function uploadImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    await ingestCatalogImage(file, event.currentTarget);
  }

  async function toggleProduct(product: AffiliateProduct) {
    setBusy(`toggle-${product.id}`);
    try {
      const updated = await updateAffiliateProduct(product.id, { is_active: !product.is_active });
      setProducts((current) => current.map((item) => item.id === updated.id ? updated : item));
      notify({ message: t("affiliateCatalog.updated"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCatalog.updateError"));
    } finally {
      setBusy(null);
    }
  }

  function toggleTopic(topicId: string) {
    setDraft((current) => ({
      ...current,
      topic_ids: current.topic_ids.includes(topicId)
        ? current.topic_ids.filter((id) => id !== topicId)
        : [...current.topic_ids, topicId],
    }));
  }

  const creating = showForm && !editingProductId;

  return (
    <OperatorStudioShell
      actions={<TopbarRefreshButton busy={loading} disabled={loading} onClick={() => void load(true)} />}
      description={t("publishingSettings.affiliateCatalogHint")}
      title={t("publishingSettings.affiliateCatalog")}
    >
      <main className="publishing-settings-page is-v1 is-v4">
        <PublishingSettingsNav />
    <section className="affiliate-catalog-page is-v10 is-v11 is-v12 is-v13 is-v14 is-v15 is-v16 is-v17 is-v18">
      {coldLoading && !showForm ? (
        <IntelligenceCatalogWorksheetSkeleton className="affiliate-catalog-loading" label={t("affiliateCatalog.title")} />
      ) : null}

      {!(coldLoading && !showForm) ? (
      <section aria-label={t("affiliateCatalog.title")} className="affiliate-catalog-toolbar">
        <div className="affiliate-catalog-toolbar__meta">
          <span className="affiliate-catalog-meta">
            <em>{t("affiliateCatalog.total")}</em>
            <b>{total}</b>
          </span>
          <span className="affiliate-catalog-meta">
            <em>{t("affiliateCatalog.active")}</em>
            <b>{activeCount}</b>
          </span>
          <span className={outOfStockCount > 0 ? "affiliate-catalog-meta is-warning" : "affiliate-catalog-meta"}>
            <em>{t("affiliateCatalog.outOfStock")}</em>
            <b>{outOfStockCount}</b>
          </span>
          <span className="affiliate-catalog-meta is-version" title="AFFILIATE_CATALOG_V1">
            <em>{t("affiliateCatalog.catalogVersion")}</em>
            <b>V1</b>
          </span>
        </div>
        <div className="affiliate-catalog-toolbar__controls">
          <label className="affiliate-catalog-toolbar__search">
            <span className="visually-hidden">{t("affiliateCatalog.search")}</span>
            <input
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("affiliateCatalog.searchPlaceholder")}
              value={query}
            />
          </label>
          <div className="affiliate-catalog-toolbar__actions">
            <AsyncButton
              aria-label={t("common.refresh")}
              className="affiliate-catalog-toolbar__icon-btn"
              leadingIcon={<CatalogGlyph kind="refresh" />}
              pending={loading}
              pendingLabel={<span className="visually-hidden">{t("common.refresh")}</span>}
              title={t("common.refresh")}
              onClick={() => void load(true)}
            >
              {t("common.refresh")}
            </AsyncButton>
            <button
              aria-expanded={showImport}
              aria-label={t("affiliateCatalog.importCsv")}
              className={`affiliate-catalog-toolbar__icon-btn${showImport ? " is-open" : ""}`}
              onClick={() => {
                setShowImport((current) => !current);
                if (!showImport) closeProductForm();
              }}
              title={t("affiliateCatalog.importCsv")}
              type="button"
            >
              <CatalogGlyph kind="import" />
            </button>
            <button
              aria-expanded={creating}
              aria-label={t("affiliateCatalog.addProduct")}
              className={`affiliate-catalog-toolbar__icon-btn is-add${creating ? " is-open" : ""}`}
              onClick={openCreateForm}
              title={t("affiliateCatalog.addProduct")}
              type="button"
            >
              <CatalogGlyph kind="plus" />
            </button>
          </div>
        </div>
      </section>
      ) : null}

      {error ? (
        <p className="affiliate-catalog-note" role="alert">
          <span>{t("affiliateCatalog.title")}</span>
          {error}
        </p>
      ) : null}

      {showForm ? (
        <section className="affiliate-catalog-form is-v12 is-v13 is-v14 is-v15">
          <header>
            <div>
              <strong>{t(editingProductId ? "affiliateCatalog.editProduct" : "affiliateCatalog.newProduct")}</strong>
              <small>{t(editingProductId ? "affiliateCatalog.editProductHint" : "affiliateCatalog.newProductHint")}</small>
            </div>
          </header>
          <div className="affiliate-catalog-form-grid">
            <label
              className={`affiliate-catalog-upload-panel is-cover${draft.image_url ? " has-image" : ""}${busy === "image-upload" ? " is-busy" : ""}`}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                const file = event.dataTransfer.files[0];
                if (file) void ingestCatalogImage(file);
              }}
              title={t("affiliateCatalog.uploadImageHint")}
            >
              <input
                accept="image/jpeg,image/png,image/webp"
                className="visually-hidden"
                disabled={busy === "image-upload"}
                onChange={(event) => void uploadImage(event)}
                type="file"
              />
              {draft.image_url ? (
                <span className="affiliate-catalog-image-preview">
                  <img alt={draft.name || t("affiliateCatalog.imageAlt")} src={affiliateImagePreviewUrl(draft.image_url)} />
                </span>
              ) : (
                <span className="affiliate-catalog-cover-empty">
                  <CatalogGlyph kind="image" />
                  <b>{busy === "image-upload" ? t("affiliateCatalog.uploadingImage") : t("affiliateCatalog.chooseImage")}</b>
                </span>
              )}
            </label>
            <label className="is-name">
              <span>{t("affiliateCatalog.name")}</span>
              <input onChange={(event) => patchDraft({ name: event.target.value })} value={draft.name} />
            </label>
            <label>
              <span>{t("affiliateCatalog.platform")}</span>
              <select onChange={(event) => patchDraft({ platform: event.target.value as AffiliatePlatform })} value={draft.platform}>
                <option value="SHOPEE">Shopee</option>
                <option value="TIKTOK_SHOP">TikTok Shop</option>
                <option value="FACEBOOK">Facebook</option>
                <option value="OTHER">Other</option>
              </select>
            </label>
            <label>
              <span>{t("affiliateCatalog.merchant")}</span>
              <input onChange={(event) => patchDraft({ merchant_name: event.target.value || null })} value={draft.merchant_name ?? ""} />
            </label>
            <label>
              <span>{t("affiliateCatalog.externalId")}</span>
              <input onChange={(event) => patchDraft({ external_product_id: event.target.value || null })} value={draft.external_product_id ?? ""} />
            </label>
            <label className="affiliate-catalog-cover-url is-wide">
              <span>{t(draft.image_url ? "affiliateCatalog.imageUrl" : "affiliateCatalog.pasteImageUrl")}</span>
              <input
                onChange={(event) => patchDraft({ image_url: event.target.value || null })}
                placeholder="https://cdn.example.com/product.jpg"
                value={draft.image_url ?? ""}
              />
            </label>
            <label className={`affiliate-catalog-affiliate-link ${draft.affiliate_url && !isPublicHttpsUrl(draft.affiliate_url) ? "is-invalid" : ""} ${deepLink.focus === "affiliate_url" ? "is-focused" : ""}`.trim()}>
              <span>{t("affiliateCatalog.affiliateUrl")}<i>{t("affiliateCatalog.required")}</i></span>
              <input
                aria-invalid={Boolean(draft.affiliate_url && !isPublicHttpsUrl(draft.affiliate_url))}
                aria-required={true}
                onChange={(event) => patchDraft({ affiliate_url: event.target.value })}
                placeholder="https://affiliate-platform.example/product/..."
                ref={affiliateUrlInputRef}
                value={draft.affiliate_url}
              />
              {draft.affiliate_url && !isPublicHttpsUrl(draft.affiliate_url) ? <em>{t("affiliateCatalog.affiliateUrlInvalid")}</em> : null}
            </label>
            <label className="is-optional">
              <span>{t("affiliateCatalog.productUrl")}<i>{t("affiliateCatalog.optional")}</i></span>
              <input onChange={(event) => patchDraft({ product_url: event.target.value || null })} placeholder="https://..." value={draft.product_url ?? ""} />
            </label>
            <div className="affiliate-catalog-form-grid__offer">
              <label>
                <span>{t("affiliateCatalog.price")}</span>
                <input min="0" onChange={(event) => patchDraft({ price_amount: event.target.value ? Number(event.target.value) : null })} type="number" value={draft.price_amount ?? ""} />
              </label>
              <label>
                <span>{t("affiliateCatalog.commission")}</span>
                <input max="100" min="0" onChange={(event) => patchDraft({ commission_rate_percent: event.target.value ? Number(event.target.value) : null })} step="0.1" type="number" value={draft.commission_rate_percent ?? ""} />
              </label>
              <label>
                <span>{t("affiliateCatalog.availability")}</span>
                <select onChange={(event) => patchDraft({ availability_status: event.target.value as AffiliateAvailability })} value={draft.availability_status}>
                  <option value="IN_STOCK">{t("affiliateCatalog.inStock")}</option>
                  <option value="UNKNOWN">{t("affiliateCatalog.unknown")}</option>
                  <option value="OUT_OF_STOCK">{t("affiliateCatalog.outOfStock")}</option>
                </select>
              </label>
            </div>
            <label className="is-wide">
              <span>{t("affiliateCatalog.description")}</span>
              <textarea onChange={(event) => patchDraft({ description: event.target.value || null })} rows={3} value={draft.description ?? ""} />
            </label>
            <label className="is-wide">
              <span>{t("affiliateCatalog.keywords")}</span>
              <input
                onChange={(event) => patchDraft({ keywords: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) })}
                placeholder={t("affiliateCatalog.keywordsPlaceholder")}
                value={(draft.keywords ?? []).join(", ")}
              />
            </label>
            <fieldset className="affiliate-catalog-topic-picker">
              <legend>{t("affiliateCatalog.topics")}</legend>
              <div>
                {topics.filter((topic) => topic.is_active).map((topic) => (
                  <button
                    aria-pressed={draft.topic_ids.includes(topic.id)}
                    className={`affiliate-catalog-topic-chip${draft.topic_ids.includes(topic.id) ? " is-on" : ""}`}
                    key={topic.id}
                    onClick={() => toggleTopic(topic.id)}
                    type="button"
                  >
                    {topic.name}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>
          <footer>
            <button className="affiliate-catalog-form__cancel" onClick={closeProductForm} type="button">
              <CatalogGlyph kind="close" />
              <span>{t("common.cancel")}</span>
            </button>
            <AsyncButton
              className="primary affiliate-catalog-form__save"
              disabled={busy === "image-upload" || !draft.name.trim() || !isPublicHttpsUrl(draft.affiliate_url)}
              leadingIcon={<CatalogGlyph kind="check" />}
              pending={busy === (editingProductId ? `update-${editingProductId}` : "create")}
              onClick={() => void saveProduct()}
            >
              {t("common.save")}
            </AsyncButton>
          </footer>
        </section>
      ) : null}

      {showImport ? (
        <section className="affiliate-catalog-import">
          <header>
            <div>
              <strong>{t("affiliateCatalog.importTitle")}</strong>
              <small>{t("affiliateCatalog.importHint")}</small>
            </div>
            <code>{CSV_HEADER}</code>
          </header>
          <textarea onChange={(event) => setCsvText(event.target.value)} placeholder={t("affiliateCatalog.csvPlaceholder")} rows={6} value={csvText} />
          <footer>
            <button className="affiliate-catalog-form__cancel" onClick={() => setShowImport(false)} type="button">
              <CatalogGlyph kind="close" />
              <span>{t("common.cancel")}</span>
            </button>
            <AsyncButton
              className="primary"
              disabled={!csvText.trim()}
              leadingIcon={<CatalogGlyph kind="check" />}
              pending={busy === "import"}
              onClick={() => void importCsv()}
            >
              {t("affiliateCatalog.importAction")}
            </AsyncButton>
          </footer>
        </section>
      ) : null}

      {!showForm && !coldLoading ? (
        !loading && products.length === 0 ? (
          <section className="affiliate-catalog-empty">
            <strong>{t("affiliateCatalog.empty")}</strong>
            <small>{t("affiliateCatalog.hint")}</small>
            <button className="primary" onClick={openCreateForm} type="button">{t("affiliateCatalog.addProduct")}</button>
          </section>
        ) : (
          <section className="affiliate-catalog-table-wrap">
            <table className="affiliate-catalog-table">
              <thead>
                <tr>
                  <th>{t("affiliateCatalog.product")}</th>
                  <th>{t("affiliateCatalog.platform")}</th>
                  <th>{t("affiliateCatalog.topics")}</th>
                  <th>{t("affiliateCatalog.commission")}</th>
                  <th>{t("affiliateCatalog.status")}</th>
                  <th>{t("affiliateCatalog.actions")}</th>
                </tr>
              </thead>
            <tbody>
              {products.map((product) => (
                <tr
                  className={`${!product.is_active ? "is-inactive" : ""} ${editingProductId === product.id ? "is-editing" : ""}`.trim()}
                  key={product.id}
                >
                  <td>
                    <div className="affiliate-catalog-product">
                      {product.image_url ? (
                        <img alt={product.name} src={affiliateImagePreviewUrl(product.image_url)} />
                      ) : (
                        <span>SKU</span>
                      )}
                      <div>
                        <span className="affiliate-catalog-product__name">
                          <strong>{product.name}</strong>
                          <a
                            aria-label={t("affiliateCatalog.openLink")}
                            className="affiliate-catalog-product__link"
                            href={product.affiliate_url}
                            rel="noreferrer"
                            target="_blank"
                            title={t("affiliateCatalog.openLink")}
                          >
                            <CatalogGlyph kind="link" />
                          </a>
                        </span>
                        <small>{product.merchant_name || product.external_product_id || product.id.slice(0, 8)}</small>
                      </div>
                    </div>
                  </td>
                  <td><span className="affiliate-catalog-platform">{PLATFORM_LABEL[product.platform] ?? product.platform}</span></td>
                  <td>
                    {product.topic_names.length ? (
                      <div className="affiliate-catalog-topic-list">
                        {product.topic_names.map((name) => <em key={name}>{name}</em>)}
                      </div>
                    ) : (
                      <small className="muted">{t("affiliateCatalog.noTopic")}</small>
                    )}
                  </td>
                  <td>
                    <div className="affiliate-catalog-metric">
                      <strong>{product.commission_rate_percent == null ? "—" : `${product.commission_rate_percent}%`}</strong>
                    </div>
                  </td>
                  <td>
                    <div className="affiliate-catalog-status-cell">
                      <span className={`affiliate-catalog-status is-${product.is_active ? product.availability_status.toLowerCase() : "inactive"}`}>
                        {product.is_active ? t(`affiliateCatalog.availabilityValue.${product.availability_status}`) : t("affiliateCatalog.inactive")}
                      </span>
                      <small>{formatDateTime(product.updated_at)}</small>
                    </div>
                  </td>
                  <td>
                    <div className="affiliate-catalog-actions">
                      <button
                        aria-label={t("affiliateCatalog.editProduct")}
                        className="affiliate-catalog-toolbar__icon-btn"
                        onClick={() => openEditForm(product)}
                        title={t("affiliateCatalog.editProduct")}
                        type="button"
                      >
                        <CatalogGlyph kind="edit" />
                      </button>
                      <AsyncButton
                        aria-label={product.is_active ? t("affiliateCatalog.deactivate") : t("affiliateCatalog.activate")}
                        className="affiliate-catalog-toolbar__icon-btn"
                        leadingIcon={<CatalogGlyph kind="power" />}
                        pending={busy === `toggle-${product.id}`}
                        pendingLabel={<span className="visually-hidden">{product.is_active ? t("affiliateCatalog.deactivate") : t("affiliateCatalog.activate")}</span>}
                        title={product.is_active ? t("affiliateCatalog.deactivate") : t("affiliateCatalog.activate")}
                        onClick={() => void toggleProduct(product)}
                      >
                        {product.is_active ? t("affiliateCatalog.deactivate") : t("affiliateCatalog.activate")}
                      </AsyncButton>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        )
      ) : null}
    </section>
      </main>
    </OperatorStudioShell>
  );
}
