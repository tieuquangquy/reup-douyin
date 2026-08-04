"use client";

import { useEffect, useState } from "react";
import {
  activateAffiliateCommentTemplate,
  createAffiliateCommentTemplate,
  deleteAffiliateCommentTemplate,
  fetchAffiliateCommentTemplates,
  reviseAffiliateCommentTemplate,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { AffiliateCommentTemplate, AffiliateCommentTemplateInput } from "../../types/affiliate-comment-template";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { PublishingSettingsNav } from "./PublishingSettingsNav";


const DEFAULT_FORM: AffiliateCommentTemplateInput = {
  name: "Facebook Reel affiliate default",
  message_template: "{{cta}}\n\n{{product_name}}\n{{description}}\n\n{{affiliate_url}}\n\n{{disclosure}}",
  default_cta: "Xem sản phẩm phù hợp với video tại:",
  default_disclosure: "Đây là liên kết tiếp thị liên kết; tôi có thể nhận hoa hồng nếu bạn mua hàng qua liên kết này.",
  attach_product_image: true,
};


export function AffiliateCommentTemplatesSettingsPage() {
  const t = useT();
  const { notify } = useNotice();
  const [templates, setTemplates] = useState<AffiliateCommentTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const response = await fetchAffiliateCommentTemplates();
      setTemplates(response.templates);
      const active = response.templates.find((item) => item.is_active) ?? response.templates[0];
      if (active) {
        setSelectedId(active.id);
        setForm({
          name: active.name,
          message_template: active.message_template,
          default_cta: active.default_cta,
          default_disclosure: active.default_disclosure,
          attach_product_image: active.attach_product_image,
        });
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCommentTemplates.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function selectTemplate(template: AffiliateCommentTemplate) {
    setSelectedId(template.id);
    setForm({
      name: template.name,
      message_template: template.message_template,
      default_cta: template.default_cta,
      default_disclosure: template.default_disclosure,
      attach_product_image: template.attach_product_image,
    });
  }

  function startNew() {
    setSelectedId(null);
    setForm({ ...DEFAULT_FORM, name: `${DEFAULT_FORM.name} ${templates.length + 1}` });
  }

  async function save(activateAfterSave = false) {
    const busyKey = activateAfterSave ? "save-activate" : "save";
    setBusy(busyKey);
    setError(null);
    try {
      const saved = selectedId
        ? await reviseAffiliateCommentTemplate(selectedId, form)
        : await createAffiliateCommentTemplate(form);
      const finalTemplate = activateAfterSave
        ? await activateAffiliateCommentTemplate(saved.id)
        : saved;
      await load();
      selectTemplate(finalTemplate);
      notify({
        message: t(activateAfterSave
          ? "affiliateCommentTemplates.savedAndActivated"
          : "affiliateCommentTemplates.saved"),
        tone: "success",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCommentTemplates.saveError"));
    } finally {
      setBusy(null);
    }
  }

  async function activate(template: AffiliateCommentTemplate) {
    setBusy(`activate-${template.id}`);
    setError(null);
    try {
      await activateAffiliateCommentTemplate(template.id);
      await load();
      notify({ message: t("affiliateCommentTemplates.activated"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCommentTemplates.activateError"));
    } finally {
      setBusy(null);
    }
  }

  async function remove(template: AffiliateCommentTemplate) {
    if (template.is_active) {
      setError(t("affiliateCommentTemplates.deleteActiveError"));
      return;
    }
    if (!window.confirm(t("affiliateCommentTemplates.deleteConfirm").replace("{name}", template.name).replace("{version}", String(template.version)))) return;
    setBusy(`delete-${template.id}`);
    setError(null);
    try {
      await deleteAffiliateCommentTemplate(template.id);
      setSelectedId(null);
      setForm({ ...DEFAULT_FORM });
      await load();
      notify({ message: t("affiliateCommentTemplates.deleted"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("affiliateCommentTemplates.deleteError"));
    } finally {
      setBusy(null);
    }
  }

  const selectedTemplate = templates.find((item) => item.id === selectedId);

  return <OperatorStudioShell description={t("affiliateCommentTemplates.description")} title={t("affiliateCommentTemplates.title")}>
    <main className="publishing-settings-page affiliate-comment-templates-page">
      <PublishingSettingsNav />
      {error ? <div className="inline-error" role="alert">{error}</div> : null}
      <section className="affiliate-comment-template-layout">
        <aside className="affiliate-comment-template-list">
          <header><strong>{t("affiliateCommentTemplates.title")}</strong><button onClick={startNew} type="button">{t("affiliateCommentTemplates.newTemplate")}</button></header>
          {loading ? <p className="muted">{t("affiliateComment.loading")}</p> : templates.length === 0 ? <p className="muted">{t("affiliateCommentTemplates.empty")}</p> : templates.map((template) => <article className={selectedId === template.id ? "is-selected" : ""} key={template.id}><button onClick={() => selectTemplate(template)} type="button"><span><strong>{template.name}</strong><small>{t("affiliateCommentTemplates.version")} {template.version}</small></span>{template.is_active ? <em>{t("affiliateCommentTemplates.active")}</em> : null}</button><AsyncButton className="affiliate-comment-template-card-delete" disabled={template.is_active} pending={busy === `delete-${template.id}`} title={template.is_active ? t("affiliateCommentTemplates.deleteActiveError") : t("affiliateCommentTemplates.delete")} onClick={() => void remove(template)}>{t("affiliateCommentTemplates.delete")}</AsyncButton></article>)}
        </aside>
        <section className="affiliate-comment-template-editor">
          <header><div><strong>{selectedId ? t("affiliateCommentTemplates.editTemplate") : t("affiliateCommentTemplates.newTemplate")}</strong><small>{t("affiliateCommentTemplates.messageHint")}</small></div><span>FACEBOOK_REELS</span></header>
          <label><span>{t("affiliateCommentTemplates.name")}</span><input onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} value={form.name} /></label>
          <label><span>{t("affiliateCommentTemplates.messageTemplate")}</span><textarea onChange={(event) => setForm((current) => ({ ...current, message_template: event.target.value }))} rows={9} value={form.message_template} /></label>
          <div className="affiliate-comment-template-grid"><label><span>{t("affiliateCommentTemplates.cta")}</span><textarea onChange={(event) => setForm((current) => ({ ...current, default_cta: event.target.value }))} rows={3} value={form.default_cta} /></label><label><span>{t("affiliateCommentTemplates.disclosure")}</span><textarea onChange={(event) => setForm((current) => ({ ...current, default_disclosure: event.target.value }))} rows={3} value={form.default_disclosure} /></label></div>
          <label className="affiliate-comment-template-attachment"><input checked={form.attach_product_image} onChange={(event) => setForm((current) => ({ ...current, attach_product_image: event.target.checked }))} type="checkbox" /><span><strong>{t("affiliateCommentTemplates.attachImage")}</strong><small>{t("affiliateCommentTemplates.attachImageHint")}</small></span></label>
          <p className="affiliate-comment-template-variable-note">{t("affiliateCommentTemplates.productImageVariable")}</p>
          <footer>
            <AsyncButton className="primary" disabled={busy !== null} pending={busy === "save"} onClick={() => void save()}>{t("affiliateCommentTemplates.save")}</AsyncButton>
            <AsyncButton disabled={busy !== null} pending={busy === "save-activate"} onClick={() => void save(true)}>{t("affiliateCommentTemplates.saveAndActivate")}</AsyncButton>
            {selectedTemplate && !selectedTemplate.is_active ? <AsyncButton disabled={busy !== null} pending={busy === `activate-${selectedTemplate.id}`} onClick={() => void activate(selectedTemplate)}>{t("affiliateCommentTemplates.activate")}</AsyncButton> : null}
          </footer>
        </section>
      </section>
    </main>
  </OperatorStudioShell>;
}
