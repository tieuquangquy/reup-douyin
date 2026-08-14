"use client";

import { useEffect, useMemo, useState } from "react";
import { createContentTopic, fetchContentTopics, updateContentTopic } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { TopicCategory } from "../../types/content-intelligence";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";
import { IntelligenceTreeSkeleton } from "./IntelligenceDataSkeleton";

type TopicEdit = {
  name: string;
  description: string;
  parentId: string;
  keywords: string;
  sortOrder: string;
  isActive: boolean;
};

function editFromTopic(topic: TopicCategory): TopicEdit {
  return {
    name: topic.name,
    description: topic.description ?? "",
    parentId: topic.parent_id ?? "",
    keywords: (topic.keywords_json ?? []).join(", "),
    sortOrder: String(topic.sort_order),
    isActive: topic.is_active,
  };
}

function keywordList(value: string): string[] {
  return [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))];
}

function TaxonomyGlyph({ kind }: { kind: "refresh" | "plus" | "chevron" | "close" | "check" }) {
  if (kind === "plus") {
    return (
      <svg aria-hidden="true" className="content-taxonomy-toolbar__glyph" fill="none" viewBox="0 0 24 24">
        <path d="M12 6.5v11M6.5 12h11" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "chevron") {
    return (
      <svg aria-hidden="true" className="content-taxonomy-row__chevron" fill="none" viewBox="0 0 24 24">
        <path d="m9 10.5 3 3 3-3" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "close") {
    return (
      <svg aria-hidden="true" className="content-taxonomy-create__glyph" fill="none" viewBox="0 0 24 24">
        <path d="m7.5 7.5 9 9M16.5 7.5l-9 9" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
      </svg>
    );
  }
  if (kind === "check") {
    return (
      <svg aria-hidden="true" className="content-taxonomy-create__glyph" fill="none" viewBox="0 0 24 24">
        <path d="m6.8 12.2 3.2 3.2 7.2-7.4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="content-taxonomy-toolbar__glyph" fill="none" viewBox="0 0 24 24">
      <path d="M19.2 8.2V12h-3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M4.8 15.8V12h3.8" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
      <path d="M7.05 9.15a6.2 6.2 0 0 1 10.4-1.75L19.2 9.15M4.8 14.85l1.75 1.75a6.2 6.2 0 0 0 10.4-1.75" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.85" />
    </svg>
  );
}

type TopicGlyphKind =
  | "food"
  | "beauty"
  | "fashion"
  | "home"
  | "tech"
  | "health"
  | "pets"
  | "travel"
  | "education"
  | "finance"
  | "entertainment"
  | "generic";

function resolveTopicGlyphKind(code: string, name: string): TopicGlyphKind {
  const hay = `${code} ${name}`.toLowerCase();
  if (/food|drink|cook|recipe|coffee|tea|restaurant|cuisine/.test(hay)) return "food";
  if (/beauty|skin|makeup|cosmetic|personal.?care/.test(hay)) return "beauty";
  if (/fashion|apparel|cloth|outfit|wear/.test(hay)) return "fashion";
  if (/home|living|furniture|appliance|interior|decor/.test(hay)) return "home";
  if (/tech|mobile|gadget|phone|computer|digital|electronics/.test(hay)) return "tech";
  if (/health|fitness|wellness|medical|gym|sport/.test(hay)) return "health";
  if (/pet|animal|dog|cat/.test(hay)) return "pets";
  if (/travel|tour|hotel|trip/.test(hay)) return "travel";
  if (/edu|learn|school|course|book/.test(hay)) return "education";
  if (/finance|money|bank|invest|insurance/.test(hay)) return "finance";
  if (/entertain|game|music|movie|film|media/.test(hay)) return "entertainment";
  return "generic";
}

function TaxonomyTopicGlyph({ kind }: { kind: TopicGlyphKind }) {
  const common = {
    "aria-hidden": true as const,
    className: "content-taxonomy-row__glyph",
    fill: "none",
    viewBox: "0 0 24 24",
  };
  if (kind === "food") {
    return (
      <svg {...common}>
        <path d="M8 4v8M8 12c0 3 1.2 6 4 8M16 4v7a3 3 0 0 1-3 3h-1" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "beauty") {
    return (
      <svg {...common}>
        <path d="M8 20c2-5 3-8 4-12 1 4 2 7 4 12" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
        <path d="M9.5 11h5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "fashion") {
    return (
      <svg {...common}>
        <path d="M9 5.5 12 8l3-2.5 2.5 2L16 10v9.5H8V10L6.5 7.5 9 5.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "home") {
    return (
      <svg {...common}>
        <path d="m4.5 11 7.5-6.5L19.5 11" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
        <path d="M7 10.5V19h10v-8.5" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "tech") {
    return (
      <svg {...common}>
        <rect height="12" rx="1.5" stroke="currentColor" strokeWidth="1.7" width="12" x="6" y="5" />
        <path d="M10 19h4M12 17v2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "health") {
    return (
      <svg {...common}>
        <path d="M12 20s-6.5-4.2-6.5-9A3.5 3.5 0 0 1 12 8.2 3.5 3.5 0 0 1 18.5 11c0 4.8-6.5 9-6.5 9Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "pets") {
    return (
      <svg {...common}>
        <circle cx="8" cy="9" r="1.4" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="16" cy="9" r="1.4" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="6.5" cy="13" r="1.3" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="17.5" cy="13" r="1.3" stroke="currentColor" strokeWidth="1.5" />
        <ellipse cx="12" cy="15.5" rx="2.6" ry="2.2" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  }
  if (kind === "travel") {
    return (
      <svg {...common}>
        <path d="M4 16.5 10.5 14 20 6.5 17.5 16 10.5 14 8 19.5" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "education") {
    return (
      <svg {...common}>
        <path d="m4 10 8-4 8 4-8 4-8-4Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
        <path d="M8 12.2V16c0 .8 1.8 2 4 2s4-1.2 4-2v-3.8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
      </svg>
    );
  }
  if (kind === "finance") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="7" stroke="currentColor" strokeWidth="1.7" />
        <path d="M12 8v8M9.5 10.2c.6-.8 1.5-1.2 2.5-1.2 1.4 0 2.4.7 2.4 1.8S13.4 12.5 12 12.5 9.5 13.2 9.5 14.4c0 1.1 1 1.8 2.5 1.8 1.1 0 2-.4 2.5-1.1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
      </svg>
    );
  }
  if (kind === "entertainment") {
    return (
      <svg {...common}>
        <rect height="12" rx="2" stroke="currentColor" strokeWidth="1.7" width="14" x="5" y="7" />
        <path d="m10 11 5 2-5 2v-4Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M7 6.5h5.2L14 8.8H17a1.5 1.5 0 0 1 1.5 1.5V17a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 17V8A1.5 1.5 0 0 1 7 6.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  );
}

export function ContentTaxonomyManager() {
  const t = useT();
  const { notify } = useNotice();
  const [topics, setTopics] = useState<TopicCategory[]>([]);
  const [taxonomyVersion, setTaxonomyVersion] = useState("CONTENT_TAXONOMY_V1");
  const [edits, setEdits] = useState<Record<string, TopicEdit>>({});
  const [loading, setLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newParentId, setNewParentId] = useState("");
  const [newKeywords, setNewKeywords] = useState("");

  async function load(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchContentTopics(true);
      setTopics(payload.topics);
      setTaxonomyVersion(payload.taxonomy_version);
      setEdits(Object.fromEntries(payload.topics.map((topic) => [topic.id, editFromTopic(topic)])));
      setHasLoadedOnce(true);
      setError(null);
      if (showNotice) notify({ message: t("contentTaxonomy.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentTaxonomy.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function patchEdit(topicId: string, patch: Partial<TopicEdit>) {
    setEdits((current) => ({ ...current, [topicId]: { ...current[topicId], ...patch } }));
  }

  async function saveTopic(topic: TopicCategory) {
    const edit = edits[topic.id];
    if (!edit?.name.trim()) return;
    setBusy(`save-${topic.id}`);
    setError(null);
    try {
      const updated = await updateContentTopic(topic.id, {
        name: edit.name.trim(),
        description: edit.description.trim() || null,
        parent_id: edit.parentId || null,
        keywords: keywordList(edit.keywords),
        sort_order: Math.max(0, Number(edit.sortOrder) || 0),
        is_active: edit.isActive,
      });
      setTopics((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEdits((current) => ({ ...current, [updated.id]: editFromTopic(updated) }));
      notify({ message: t("contentTaxonomy.saved"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentTaxonomy.saveError"));
    } finally {
      setBusy(null);
    }
  }

  async function addTopic() {
    if (!newCode.trim() || !newName.trim()) return;
    setBusy("create");
    setError(null);
    try {
      await createContentTopic({
        code: newCode.trim().toUpperCase().replace(/[^A-Z0-9]+/g, "_"),
        name: newName.trim(),
        parent_id: newParentId || null,
        keywords: keywordList(newKeywords),
        sort_order: topics.length ? Math.max(...topics.map((topic) => topic.sort_order)) + 1 : 0,
      });
      setNewCode("");
      setNewName("");
      setNewParentId("");
      setNewKeywords("");
      setCreateOpen(false);
      await load();
      notify({ message: t("contentTaxonomy.created"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentTaxonomy.createError"));
    } finally {
      setBusy(null);
    }
  }

  const topicById = useMemo(() => new Map(topics.map((topic) => [topic.id, topic])), [topics]);
  const rootTopics = topics.filter((topic) => !topic.parent_id);
  const ungrouped = topics.filter((topic) => topic.parent_id && !topicById.has(topic.parent_id));
  const activeCount = topics.filter((topic) => topic.is_active).length;
  const inactiveCount = topics.length - activeCount;
  const coldLoading = loading && !hasLoadedOnce;

  function renderTopicRow(topic: TopicCategory) {
    const edit = edits[topic.id] ?? editFromTopic(topic);
    const isChild = Boolean(topic.parent_id);
    const isExpanded = expandedId === topic.id;
    const changed = JSON.stringify(edit) !== JSON.stringify(editFromTopic(topic));
    const keywords = (() => {
      const fromEdit = keywordList(edit.keywords);
      if (fromEdit.length) return fromEdit;
      return topic.keywords_json ?? [];
    })();
    const keywordCount = keywords.length;
    const keywordChips = keywords.slice(0, 3);
    const keywordOverflow = Math.max(0, keywordCount - keywordChips.length);
    const glyphKind = resolveTopicGlyphKind(topic.code, edit.name || topic.name);

    return (
      <article
        className={`content-taxonomy-row ${isChild ? "is-child" : "is-root"} ${edit.isActive ? "is-active" : "is-inactive"}${isExpanded ? " is-expanded" : ""}`}
        key={topic.id}
      >
        <div className="content-taxonomy-row__summary">
          <button
            aria-expanded={isExpanded}
            aria-label={`${isExpanded ? t("contentTaxonomy.collapse") : t("contentTaxonomy.edit")}: ${edit.name || topic.name}`}
            className="content-taxonomy-row__toggle"
            onClick={() => setExpandedId(isExpanded ? null : topic.id)}
            type="button"
          >
            {isChild ? <i aria-hidden="true" className="content-taxonomy-row__rail" /> : null}
            <span className={`content-taxonomy-row__icon is-${glyphKind}${isChild ? " is-child" : " is-root"}`}>
              <TaxonomyTopicGlyph kind={glyphKind} />
            </span>
            <span className="content-taxonomy-row__copy">
              <strong className="content-taxonomy-row__name">{edit.name || topic.name}</strong>
              <small className="content-taxonomy-row__code">{topic.code}</small>
            </span>
            <TaxonomyGlyph kind="chevron" />
          </button>
          <div className="content-taxonomy-row__chips" aria-label={t("contentTaxonomy.keywords")}>
            {keywordChips.length === 0 ? (
              <span className="content-taxonomy-row__chip is-empty">—</span>
            ) : (
              <>
                {keywordChips.map((keyword) => (
                  <span className="content-taxonomy-row__chip" key={`${topic.id}-${keyword}`}>
                    {keyword}
                  </span>
                ))}
                {keywordOverflow > 0 ? (
                  <span className="content-taxonomy-row__chip is-more">+{keywordOverflow}</span>
                ) : null}
              </>
            )}
          </div>
          <div className="content-taxonomy-row__meta">
            <button
              aria-checked={edit.isActive}
              aria-label={edit.isActive ? t("contentTaxonomy.enabled") : t("contentTaxonomy.disabled")}
              className={`content-taxonomy-row__switch${edit.isActive ? " is-on" : ""}`}
              onClick={() => {
                patchEdit(topic.id, { isActive: !edit.isActive });
                if (!isExpanded) setExpandedId(topic.id);
              }}
              role="switch"
              title={edit.isActive ? t("contentTaxonomy.enabled") : t("contentTaxonomy.disabled")}
              type="button"
            >
              <i aria-hidden="true" />
            </button>
          </div>
        </div>

        {isExpanded ? (
          <div className="content-taxonomy-row__editor is-v19 is-v21">
            <div className="content-taxonomy-fields is-v19 is-v21">
              <label className="content-taxonomy-fields__field is-name">
                <span>{t("contentTaxonomy.name")}</span>
                <input onChange={(event) => patchEdit(topic.id, { name: event.target.value })} value={edit.name} />
              </label>
              <label className="content-taxonomy-fields__field is-parent">
                <span>{t("contentTaxonomy.parent")}</span>
                <select onChange={(event) => patchEdit(topic.id, { parentId: event.target.value })} value={edit.parentId}>
                  <option value="">{t("contentTaxonomy.noParent")}</option>
                  {rootTopics
                    .filter((parent) => parent.id !== topic.id)
                    .map((parent) => (
                      <option key={parent.id} value={parent.id}>
                        {parent.name}
                      </option>
                    ))}
                </select>
              </label>
              <label className="content-taxonomy-fields__field is-order">
                <span>{t("contentTaxonomy.order")}</span>
                <input
                  min="0"
                  onChange={(event) => patchEdit(topic.id, { sortOrder: event.target.value })}
                  type="number"
                  value={edit.sortOrder}
                />
              </label>
              <label className="content-taxonomy-fields__field is-keywords">
                <span>{t("contentTaxonomy.keywords")}</span>
                <input onChange={(event) => patchEdit(topic.id, { keywords: event.target.value })} value={edit.keywords} />
              </label>
              <label className="content-taxonomy-fields__field is-description">
                <span>{t("contentTaxonomy.description")}</span>
                <input
                  onChange={(event) => patchEdit(topic.id, { description: event.target.value })}
                  value={edit.description}
                />
              </label>
            </div>
            <footer className="content-taxonomy-row__editor-actions">
              <small className="content-taxonomy-row__keyword-count">
                <b>{keywordCount}</b> {t("contentTaxonomy.keywordCount")}
              </small>
              <AsyncButton
                className="primary content-taxonomy-row__save"
                disabled={!changed || !edit.name.trim()}
                leadingIcon={<TaxonomyGlyph kind="check" />}
                pending={busy === `save-${topic.id}`}
                pendingLabel={t("common.save")}
                onClick={() => void saveTopic(topic)}
              >
                {t("common.save")}
              </AsyncButton>
            </footer>
          </div>
        ) : null}
      </article>
    );
  }

  return (
    <section className="content-taxonomy-page is-v10 is-v11 is-v12 is-v13 is-v14 is-v15 is-v16 is-v17 is-v18 is-v19 is-v20 is-v21">
      <section className="content-taxonomy-toolbar" aria-label={t("contentTaxonomy.title")}>
        <div className="content-taxonomy-toolbar__meta">
          <span className="content-taxonomy-meta is-total">
            <em>{t("contentTaxonomy.total")}</em>
            <b>{topics.length}</b>
          </span>
          <span className="content-taxonomy-meta is-active">
            <em>{t("contentTaxonomy.active")}</em>
            <b>{activeCount}</b>
          </span>
          <span className="content-taxonomy-meta is-inactive">
            <em>{t("contentTaxonomy.inactive")}</em>
            <b>{inactiveCount}</b>
          </span>
          <span className="content-taxonomy-meta is-version" title={taxonomyVersion}>
            <em>{t("contentTaxonomy.version")}</em>
            <b>{taxonomyVersion}</b>
          </span>
        </div>
        <div className="content-taxonomy-toolbar__actions">
          <AsyncButton
            aria-label={t("common.refresh")}
            className="content-taxonomy-toolbar__icon-btn is-refresh"
            leadingIcon={<TaxonomyGlyph kind="refresh" />}
            pending={loading}
            pendingLabel={<span className="visually-hidden">{t("common.refresh")}</span>}
            title={t("common.refresh")}
            onClick={() => void load(true)}
          >
            <span className="visually-hidden">{t("common.refresh")}</span>
          </AsyncButton>
          <button
            aria-expanded={createOpen}
            aria-label={t("contentTaxonomy.add")}
            className={`content-taxonomy-toolbar__icon-btn is-add${createOpen ? " is-open" : ""}`}
            onClick={() => setCreateOpen((current) => !current)}
            title={t("contentTaxonomy.add")}
            type="button"
          >
            <TaxonomyGlyph kind="plus" />
            <span className="visually-hidden">{t("contentTaxonomy.add")}</span>
          </button>
        </div>
      </section>

      {error ? (
        <div className="inline-error" role="alert">
          {error}
        </div>
      ) : null}

      {createOpen ? (
        <section className="content-taxonomy-create is-v10 is-v16 is-v18 is-v21">
          <header>
            <div>
              <strong>{t("contentTaxonomy.newTopic")}</strong>
              <small>{t("contentTaxonomy.newTopicHint")}</small>
            </div>
          </header>
          <div className="content-taxonomy-create__fields">
            <label className="content-taxonomy-create__field is-code">
              <span>{t("contentTaxonomy.code")}</span>
              <input
                autoCapitalize="characters"
                onChange={(event) => setNewCode(event.target.value)}
                placeholder="COFFEE_DRINKS"
                spellCheck={false}
                value={newCode}
              />
            </label>
            <label className="content-taxonomy-create__field is-name">
              <span>{t("contentTaxonomy.name")}</span>
              <input onChange={(event) => setNewName(event.target.value)} value={newName} />
            </label>
            <label className="content-taxonomy-create__field is-parent">
              <span>{t("contentTaxonomy.parent")}</span>
              <select onChange={(event) => setNewParentId(event.target.value)} value={newParentId}>
                <option value="">{t("contentTaxonomy.noParent")}</option>
                {rootTopics.map((topic) => (
                  <option key={topic.id} value={topic.id}>
                    {topic.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="content-taxonomy-create__field is-keywords is-wide">
              <span>{t("contentTaxonomy.keywords")}</span>
              <input
                onChange={(event) => setNewKeywords(event.target.value)}
                placeholder={t("contentTaxonomy.keywordsPlaceholder")}
                value={newKeywords}
              />
            </label>
          </div>
          <footer className="content-taxonomy-create__actions">
            <button className="content-taxonomy-create__cancel" onClick={() => setCreateOpen(false)} type="button">
              <TaxonomyGlyph kind="close" />
              <span>{t("common.cancel")}</span>
            </button>
            <AsyncButton
              className="primary content-taxonomy-create__submit"
              disabled={!newCode.trim() || !newName.trim()}
              leadingIcon={<TaxonomyGlyph kind="check" />}
              pending={busy === "create"}
              pendingLabel={t("contentTaxonomy.create")}
              onClick={() => void addTopic()}
            >
              {t("contentTaxonomy.create")}
            </AsyncButton>
          </footer>
        </section>
      ) : null}

      {coldLoading ? (
        <IntelligenceTreeSkeleton className="content-taxonomy-loading" label={t("contentTaxonomy.loading")} />
      ) : topics.length === 0 ? (
        <section className="content-taxonomy-empty">
          <strong>{t("contentTaxonomy.empty")}</strong>
          <small>{t("contentTaxonomy.emptyHint")}</small>
          <button className="primary" onClick={() => setCreateOpen(true)} type="button">
            {t("contentTaxonomy.add")}
          </button>
        </section>
      ) : (
        <section className="content-taxonomy-tree" aria-label={t("contentTaxonomy.title")}>
          {rootTopics.map((root) => {
            const children = topics.filter((topic) => topic.parent_id === root.id);
            return (
              <section className="content-taxonomy-group" key={root.id}>
                {renderTopicRow(root)}
                {children.map((child) => renderTopicRow(child))}
              </section>
            );
          })}
          {ungrouped.length > 0 ? (
            <section className="content-taxonomy-group is-orphan">
              {ungrouped.map((topic) => renderTopicRow(topic))}
            </section>
          ) : null}
        </section>
      )}
    </section>
  );
}
