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
import { formatDateTime } from "../ops-console/OpsShared";


const EMPTY_DRAFT: AffiliateProductInput = {
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
  const [draft, setDraft] = useState<AffiliateProductInput>(EMPTY_DRAFT);
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
  const originalDraftRef = useRef<AffiliateProductInput | null>(null);
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

  function patchDraft(patch: Partial<AffiliateProductInput>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function openCreateForm() {
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
    const nextDraft: AffiliateProductInput = {
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

  async function uploadImage(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      setError(t("affiliateCatalog.imageTooLarge"));
      input.value = "";
      return;
    }
    if (!(["image/jpeg", "image/png", "image/webp"] as string[]).includes(file.type.toLowerCase())) {
      setError(t("affiliateCatalog.imageUploadError"));
      input.value = "";
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
      input.value = "";
    }
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

  function topicSelection(event: ChangeEvent<HTMLSelectElement>) {
    setDraft((current) => ({ ...current, topic_ids: Array.from(event.target.selectedOptions, (option) => option.value) }));
  }

  return <section className="affiliate-catalog-page">
    <header className="affiliate-catalog-header"><div><span>{t("affiliateCatalog.eyebrow")}</span><strong>{t("affiliateCatalog.title")}</strong><small>{t("affiliateCatalog.hint")}</small></div><div><AsyncButton pending={loading} onClick={() => void load(true)}>{t("common.refresh")}</AsyncButton><button onClick={() => setShowImport((current) => !current)} type="button">{t("affiliateCatalog.importCsv")}</button><button className="primary" onClick={openCreateForm} type="button">{t("affiliateCatalog.addProduct")}</button></div></header>
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    {showForm ? <section className="affiliate-catalog-upload-panel"><div><strong>{t("affiliateCatalog.uploadImage")}</strong><small>{t("affiliateCatalog.uploadImageHint")}</small></div><label><span>{busy === "image-upload" ? t("affiliateCatalog.uploadingImage") : t("affiliateCatalog.chooseImage")}</span><input accept="image/jpeg,image/png,image/webp" disabled={busy === "image-upload"} onChange={(event) => void uploadImage(event)} type="file" /></label></section> : null}
    <section className="affiliate-catalog-kpis"><article><span>{t("affiliateCatalog.total")}</span><strong>{total}</strong><small>{t("affiliateCatalog.totalHint")}</small></article><article className="is-good"><span>{t("affiliateCatalog.active")}</span><strong>{activeCount}</strong><small>{t("affiliateCatalog.activeHint")}</small></article><article className="is-warning"><span>{t("affiliateCatalog.outOfStock")}</span><strong>{outOfStockCount}</strong><small>{t("affiliateCatalog.outOfStockHint")}</small></article></section>
    {showForm ? <section className="affiliate-catalog-form"><header><strong>{t(editingProductId ? "affiliateCatalog.editProduct" : "affiliateCatalog.newProduct")}</strong><small>{t(editingProductId ? "affiliateCatalog.editProductHint" : "affiliateCatalog.newProductHint")}</small></header><div className="affiliate-catalog-form-grid"><label><span>{t("affiliateCatalog.name")}</span><input onChange={(event) => patchDraft({ name: event.target.value })} value={draft.name} /></label><label><span>{t("affiliateCatalog.platform")}</span><select onChange={(event) => patchDraft({ platform: event.target.value as AffiliatePlatform })} value={draft.platform}><option value="SHOPEE">Shopee</option><option value="TIKTOK_SHOP">TikTok Shop</option><option value="FACEBOOK">Facebook</option><option value="OTHER">Other</option></select></label><label><span>{t("affiliateCatalog.merchant")}</span><input onChange={(event) => patchDraft({ merchant_name: event.target.value || null })} value={draft.merchant_name ?? ""} /></label><label><span>{t("affiliateCatalog.externalId")}</span><input onChange={(event) => patchDraft({ external_product_id: event.target.value || null })} value={draft.external_product_id ?? ""} /></label><label className={`is-wide affiliate-catalog-affiliate-link ${draft.affiliate_url && !isPublicHttpsUrl(draft.affiliate_url) ? "is-invalid" : ""} ${deepLink.focus === "affiliate_url" ? "is-focused" : ""}`}><span>{t("affiliateCatalog.affiliateUrl")}</span><input aria-invalid={Boolean(draft.affiliate_url && !isPublicHttpsUrl(draft.affiliate_url))} ref={affiliateUrlInputRef} onChange={(event) => patchDraft({ affiliate_url: event.target.value })} placeholder="https://affiliate-platform.example/product/..." value={draft.affiliate_url} /><small>{t("affiliateCatalog.affiliateUrlHint")}</small>{draft.affiliate_url && !isPublicHttpsUrl(draft.affiliate_url) ? <em>{t("affiliateCatalog.affiliateUrlInvalid")}</em> : null}</label><label className="is-wide"><span>{t("affiliateCatalog.imageUrl")}</span><input onChange={(event) => patchDraft({ image_url: event.target.value || null })} placeholder="https://cdn.example.com/product.jpg" value={draft.image_url ?? ""} /><small>{t("affiliateCatalog.imageUrlHint")}</small></label>{draft.image_url ? <div className="affiliate-catalog-image-preview"><img alt={draft.name || t("affiliateCatalog.imageAlt")} src={affiliateImagePreviewUrl(draft.image_url)} /><span>{t("affiliateCatalog.imagePreview")}</span></div> : null}<label className="is-wide"><span>{t("affiliateCatalog.productUrl")}</span><input onChange={(event) => patchDraft({ product_url: event.target.value || null })} placeholder="https://..." value={draft.product_url ?? ""} /></label><label className="is-wide"><span>{t("affiliateCatalog.description")}</span><textarea onChange={(event) => patchDraft({ description: event.target.value || null })} value={draft.description ?? ""} /></label><label><span>{t("affiliateCatalog.price")}</span><input min="0" onChange={(event) => patchDraft({ price_amount: event.target.value ? Number(event.target.value) : null })} type="number" value={draft.price_amount ?? ""} /></label><label><span>{t("affiliateCatalog.commission")}</span><input min="0" max="100" onChange={(event) => patchDraft({ commission_rate_percent: event.target.value ? Number(event.target.value) : null })} step="0.1" type="number" value={draft.commission_rate_percent ?? ""} /></label><label><span>{t("affiliateCatalog.availability")}</span><select onChange={(event) => patchDraft({ availability_status: event.target.value as AffiliateAvailability })} value={draft.availability_status}><option value="IN_STOCK">{t("affiliateCatalog.inStock")}</option><option value="UNKNOWN">{t("affiliateCatalog.unknown")}</option><option value="OUT_OF_STOCK">{t("affiliateCatalog.outOfStock")}</option></select></label><label className="is-wide"><span>{t("affiliateCatalog.keywords")}</span><input onChange={(event) => patchDraft({ keywords: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) })} placeholder={t("affiliateCatalog.keywordsPlaceholder")} value={(draft.keywords ?? []).join(", ")} /></label><label className="is-wide"><span>{t("affiliateCatalog.topics")}</span><select multiple onChange={topicSelection} value={draft.topic_ids}>{topics.filter((topic) => topic.is_active).map((topic) => <option key={topic.id} value={topic.id}>{topic.name} · {topic.code}</option>)}</select><small>{t("affiliateCatalog.topicHint")}</small></label></div><footer><button onClick={closeProductForm} type="button">{t("common.cancel")}</button><AsyncButton className="primary" disabled={busy === "image-upload" || !draft.name.trim() || !isPublicHttpsUrl(draft.affiliate_url)} pending={busy === (editingProductId ? `update-${editingProductId}` : "create")} onClick={() => void saveProduct()}>{t("common.save")}</AsyncButton></footer></section> : null}
    {showImport ? <section className="affiliate-catalog-import"><header><div><strong>{t("affiliateCatalog.importTitle")}</strong><small>{t("affiliateCatalog.importHint")}</small></div><code>platform,external_product_id,merchant_name,name,description,image_url,product_url,affiliate_url,currency_code,price_amount,commission_rate_percent,availability_status,keywords,supported_platforms,topic_codes,is_active</code></header><textarea onChange={(event) => setCsvText(event.target.value)} placeholder={t("affiliateCatalog.csvPlaceholder")} rows={6} value={csvText} /><footer><button onClick={() => setShowImport(false)} type="button">{t("common.cancel")}</button><AsyncButton className="primary" disabled={!csvText.trim()} pending={busy === "import"} onClick={() => void importCsv()}>{t("affiliateCatalog.importAction")}</AsyncButton></footer></section> : null}
    <section className="affiliate-catalog-toolbar"><label><span>{t("affiliateCatalog.search")}</span><input onChange={(event) => setQuery(event.target.value)} placeholder={t("affiliateCatalog.searchPlaceholder")} value={query} /></label><small>{t("affiliateCatalog.catalogVersion")} · AFFILIATE_CATALOG_V1</small></section>
    <section className="affiliate-catalog-table-wrap"><table className="affiliate-catalog-table"><thead><tr><th>{t("affiliateCatalog.product")}</th><th>{t("affiliateCatalog.platform")}</th><th>{t("affiliateCatalog.topics")}</th><th>{t("affiliateCatalog.commission")}</th><th>{t("affiliateCatalog.status")}</th><th>{t("affiliateCatalog.actions")}</th></tr></thead><tbody>{products.map((product) => <tr className={!product.is_active ? "is-inactive" : ""} key={product.id}><td><div className="affiliate-catalog-product">{product.image_url ? <img alt={product.name} src={affiliateImagePreviewUrl(product.image_url)} /> : <span>SKU</span>}<div><strong>{product.name}</strong><small>{product.merchant_name || product.external_product_id || product.id.slice(0, 8)}</small><a href={product.affiliate_url} rel="noreferrer" target="_blank">{t("affiliateCatalog.openLink")}</a></div></div></td><td><span className="affiliate-catalog-platform">{product.platform}</span></td><td>{product.topic_names.length ? <div className="affiliate-catalog-topic-list">{product.topic_names.map((name) => <em key={name}>{name}</em>)}</div> : <small className="muted">{t("affiliateCatalog.noTopic")}</small>}</td><td><strong>{product.commission_rate_percent == null ? "—" : `${product.commission_rate_percent}%`}</strong><small>{product.price_amount == null ? "" : `${new Intl.NumberFormat().format(product.price_amount)} ${product.currency_code}`}</small></td><td><span className={`affiliate-catalog-status is-${product.is_active ? product.availability_status.toLowerCase() : "inactive"}`}>{product.is_active ? t(`affiliateCatalog.availabilityValue.${product.availability_status}`) : t("affiliateCatalog.inactive")}</span><small>{formatDateTime(product.updated_at)}</small></td><td><div className="affiliate-catalog-actions"><button onClick={() => openEditForm(product)} type="button">{t("affiliateCatalog.editProduct")}</button><AsyncButton pending={busy === `toggle-${product.id}`} onClick={() => void toggleProduct(product)}>{product.is_active ? t("affiliateCatalog.deactivate") : t("affiliateCatalog.activate")}</AsyncButton></div></td></tr>)}</tbody></table>{!loading && products.length === 0 ? <p className="muted affiliate-catalog-empty">{t("affiliateCatalog.empty")}</p> : null}</section>
  </section>;
}
