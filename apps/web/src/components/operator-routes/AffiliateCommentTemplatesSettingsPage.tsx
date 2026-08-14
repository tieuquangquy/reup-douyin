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
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { IntelligenceSplitEditorSkeleton } from "./IntelligenceDataSkeleton";
import { PublishingSettingsNav } from "./PublishingSettingsNav";


const DEFAULT_FORM: AffiliateCommentTemplateInput = {
  name: "Facebook Reel affiliate default",
  message_template: "{{cta}}\n\n{{product_name}}\n{{description}}\n\n{{affiliate_url}}\n\n{{disclosure}}",
  default_cta: "Xem sản phẩm phù hợp với video tại:",
  default_disclosure: "Đây là liên kết tiếp thị liên kết; tôi có thể nhận hoa hồng nếu bạn mua hàng qua liên kết này.",
  attach_product_image: true,
};


type CommentTemplateGlyphKind = "plus" | "delete" | "save" | "check";


function CommentTemplateGlyph({ kind }: { kind: CommentTemplateGlyphKind }) {
  const common = {
    "aria-hidden": true as const,
    className: "affiliate-comment-template-glyph",
    fill: "none",
    viewBox: "0 0 24 24",
  };
  if (kind === "delete") {
    return (
      <svg {...common}>
        <path d="M8 7.5h8M10 7.5V6.4h4V7.5M9.2 7.5l.6 10.2h4.4l.6-10.2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      </svg>
    );
  }
  if (kind === "save") {
    return (
      <svg {...common}>
        <path d="M6 5.5h9.2L17.5 7.8V18.5H6V5.5z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.85" />
        <path d="M9 5.5v4.2h6.2V5.5M9 18.5v-4.6h7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
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
  return (
    <svg {...common}>
      <path d="M12 6.5v11M6.5 12h11" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  );
}


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

  return (
    <OperatorStudioShell
      actions={<TopbarRefreshButton busy={loading} disabled={loading} onClick={() => void load()} />}
      description={t("publishingSettings.affiliateCommentsHint")}
      title={t("publishingSettings.affiliateComments")}
    >
      <main className="publishing-settings-page is-v1 is-v4">
        <PublishingSettingsNav />
        {error ? (
          <p className="affiliate-comment-template-note" role="alert">
            <span>{t("affiliateCommentTemplates.title")}</span>
            {error}
          </p>
        ) : null}
        {loading ? (
          <IntelligenceSplitEditorSkeleton label={t("affiliateComment.loading")} />
        ) : (
          <section className="affiliate-comment-templates-page is-v1">
            <div className="affiliate-comment-template-layout">
              <aside className="affiliate-comment-template-list">
                <header>
                  <strong>{t("affiliateCommentTemplates.title")}</strong>
                  <button
                    aria-label={t("affiliateCommentTemplates.newTemplate")}
                    className="affiliate-comment-template-icon-btn is-add"
                    onClick={startNew}
                    title={t("affiliateCommentTemplates.newTemplate")}
                    type="button"
                  >
                    <CommentTemplateGlyph kind="plus" />
                  </button>
                </header>
                {templates.length === 0 ? (
                  <p className="affiliate-comment-template-list__empty">{t("affiliateCommentTemplates.empty")}</p>
                ) : (
                  templates.map((template) => (
                    <article
                      className={`affiliate-comment-template-list__row${selectedId === template.id ? " is-selected" : ""}`}
                      key={template.id}
                    >
                      <button onClick={() => selectTemplate(template)} type="button">
                        <span>
                          <strong>{template.name}</strong>
                          <small>
                            {t("affiliateCommentTemplates.version")} {template.version}
                          </small>
                        </span>
                        {template.is_active ? <em>{t("affiliateCommentTemplates.active")}</em> : null}
                      </button>
                      <AsyncButton
                        aria-label={t("affiliateCommentTemplates.delete")}
                        className="affiliate-comment-template-icon-btn is-delete"
                        disabled={template.is_active}
                        leadingIcon={<CommentTemplateGlyph kind="delete" />}
                        pending={busy === `delete-${template.id}`}
                        pendingLabel={<span className="visually-hidden">{t("affiliateCommentTemplates.delete")}</span>}
                        title={template.is_active ? t("affiliateCommentTemplates.deleteActiveError") : t("affiliateCommentTemplates.delete")}
                        onClick={() => void remove(template)}
                      >
                        {t("affiliateCommentTemplates.delete")}
                      </AsyncButton>
                    </article>
                  ))
                )}
              </aside>

              <section className="affiliate-comment-template-editor">
                <header>
                  <div>
                    <strong>{selectedId ? t("affiliateCommentTemplates.editTemplate") : t("affiliateCommentTemplates.newTemplate")}</strong>
                    <small>{t("affiliateCommentTemplates.messageHint")}</small>
                  </div>
                  <span className="affiliate-comment-template-editor__channel">FACEBOOK_REELS</span>
                </header>

                <div className="affiliate-comment-template-editor__body">
                  <label className="affiliate-comment-template-field is-name">
                    <span>{t("affiliateCommentTemplates.name")}</span>
                    <input
                      onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                      value={form.name}
                    />
                  </label>
                  <label className="affiliate-comment-template-field is-message">
                    <span>{t("affiliateCommentTemplates.messageTemplate")}</span>
                    <textarea
                      onChange={(event) => setForm((current) => ({ ...current, message_template: event.target.value }))}
                      rows={9}
                      value={form.message_template}
                    />
                  </label>
                  <div className="affiliate-comment-template-grid">
                    <label className="affiliate-comment-template-field">
                      <span>{t("affiliateCommentTemplates.cta")}</span>
                      <textarea
                        onChange={(event) => setForm((current) => ({ ...current, default_cta: event.target.value }))}
                        rows={3}
                        value={form.default_cta}
                      />
                    </label>
                    <label className="affiliate-comment-template-field">
                      <span>{t("affiliateCommentTemplates.disclosure")}</span>
                      <textarea
                        onChange={(event) => setForm((current) => ({ ...current, default_disclosure: event.target.value }))}
                        rows={3}
                        value={form.default_disclosure}
                      />
                    </label>
                  </div>
                  <label className="affiliate-comment-template-attachment">
                    <input
                      checked={form.attach_product_image}
                      onChange={(event) => setForm((current) => ({ ...current, attach_product_image: event.target.checked }))}
                      type="checkbox"
                    />
                    <span>
                      <strong>{t("affiliateCommentTemplates.attachImage")}</strong>
                      <small>{t("affiliateCommentTemplates.attachImageHint")}</small>
                    </span>
                  </label>
                  <p className="affiliate-comment-template-note is-hint">{t("affiliateCommentTemplates.productImageVariable")}</p>
                </div>

                <footer className="affiliate-comment-template-editor__footer">
                  <AsyncButton
                    className="primary"
                    disabled={busy !== null}
                    leadingIcon={<CommentTemplateGlyph kind="save" />}
                    pending={busy === "save"}
                    onClick={() => void save()}
                  >
                    {t("affiliateCommentTemplates.save")}
                  </AsyncButton>
                  <AsyncButton
                    disabled={busy !== null}
                    leadingIcon={<CommentTemplateGlyph kind="check" />}
                    pending={busy === "save-activate"}
                    onClick={() => void save(true)}
                  >
                    {t("affiliateCommentTemplates.saveAndActivate")}
                  </AsyncButton>
                  {selectedTemplate && !selectedTemplate.is_active ? (
                    <AsyncButton
                      disabled={busy !== null}
                      leadingIcon={<CommentTemplateGlyph kind="check" />}
                      pending={busy === `activate-${selectedTemplate.id}`}
                      onClick={() => void activate(selectedTemplate)}
                    >
                      {t("affiliateCommentTemplates.activate")}
                    </AsyncButton>
                  ) : null}
                </footer>
              </section>
            </div>
          </section>
        )}
      </main>
    </OperatorStudioShell>
  );
}
