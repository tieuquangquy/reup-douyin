"use client";

import { useEffect, useMemo, useState } from "react";
import { createContentTopic, fetchContentTopics, updateContentTopic } from "../../lib/api";
import { useT } from "../../lib/i18n";
import type { TopicCategory } from "../../types/content-intelligence";
import { AsyncButton } from "../shared/AsyncButton";
import { useNotice } from "../shared/NoticeCenter";


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


export function ContentTaxonomyManager() {
  const t = useT();
  const { notify } = useNotice();
  const [topics, setTopics] = useState<TopicCategory[]>([]);
  const [edits, setEdits] = useState<Record<string, TopicEdit>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newName, setNewName] = useState("");
  const [newParentId, setNewParentId] = useState("");
  const [newKeywords, setNewKeywords] = useState("");

  async function load(showNotice = false) {
    setLoading(true);
    try {
      const payload = await fetchContentTopics(true);
      setTopics(payload.topics);
      setEdits(Object.fromEntries(payload.topics.map((topic) => [topic.id, editFromTopic(topic)])));
      setError(null);
      if (showNotice) notify({ message: t("contentTaxonomy.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("contentTaxonomy.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

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
      setTopics((current) => current.map((item) => item.id === updated.id ? updated : item));
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
  const orderedTopics = rootTopics.flatMap((root) => [root, ...topics.filter((topic) => topic.parent_id === root.id)]);
  const ungrouped = topics.filter((topic) => topic.parent_id && !topicById.has(topic.parent_id));

  return <section className="content-taxonomy-page">
    <header><div><span>{t("contentTaxonomy.eyebrow")}</span><strong>{t("contentTaxonomy.title")}</strong><small>{t("contentTaxonomy.hint")}</small></div><div><AsyncButton pending={loading} onClick={() => void load(true)}>{t("common.refresh")}</AsyncButton><button className="primary" onClick={() => setCreateOpen((current) => !current)} type="button">{t("contentTaxonomy.add")}</button></div></header>
    {error ? <div className="inline-error" role="alert">{error}</div> : null}
    <section className="content-taxonomy-summary"><article><span>{t("contentTaxonomy.version")}</span><strong>CONTENT_TAXONOMY_V1</strong></article><article><span>{t("contentTaxonomy.total")}</span><strong>{topics.length}</strong></article><article><span>{t("contentTaxonomy.active")}</span><strong>{topics.filter((topic) => topic.is_active).length}</strong></article><article><span>{t("contentTaxonomy.inactive")}</span><strong>{topics.filter((topic) => !topic.is_active).length}</strong></article></section>
    {createOpen ? <section className="content-taxonomy-create"><header><strong>{t("contentTaxonomy.newTopic")}</strong><small>{t("contentTaxonomy.newTopicHint")}</small></header><div><label><span>{t("contentTaxonomy.code")}</span><input onChange={(event) => setNewCode(event.target.value)} placeholder="COFFEE_DRINKS" value={newCode} /></label><label><span>{t("contentTaxonomy.name")}</span><input onChange={(event) => setNewName(event.target.value)} value={newName} /></label><label><span>{t("contentTaxonomy.parent")}</span><select onChange={(event) => setNewParentId(event.target.value)} value={newParentId}><option value="">{t("contentTaxonomy.noParent")}</option>{rootTopics.map((topic) => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label><label className="is-wide"><span>{t("contentTaxonomy.keywords")}</span><input onChange={(event) => setNewKeywords(event.target.value)} placeholder={t("contentTaxonomy.keywordsPlaceholder")} value={newKeywords} /></label></div><footer><button onClick={() => setCreateOpen(false)} type="button">{t("common.cancel")}</button><AsyncButton className="primary" disabled={!newCode.trim() || !newName.trim()} pending={busy === "create"} onClick={() => void addTopic()}>{t("contentTaxonomy.create")}</AsyncButton></footer></section> : null}
    {loading && topics.length === 0 ? <p className="muted">{t("contentTaxonomy.loading")}</p> : <section className="content-taxonomy-list">{[...orderedTopics, ...ungrouped].map((topic) => {
      const edit = edits[topic.id] ?? editFromTopic(topic);
      const isChild = Boolean(topic.parent_id);
      const changed = JSON.stringify(edit) !== JSON.stringify(editFromTopic(topic));
      return <article className={`${isChild ? "is-child" : "is-root"} ${edit.isActive ? "is-active" : "is-inactive"}`} key={topic.id}><header><div><span>{isChild ? t("contentTaxonomy.child") : t("contentTaxonomy.root")}</span><strong>{topic.code}</strong></div><label><input checked={edit.isActive} onChange={(event) => patchEdit(topic.id, { isActive: event.target.checked })} type="checkbox" /><span>{edit.isActive ? t("contentTaxonomy.enabled") : t("contentTaxonomy.disabled")}</span></label></header><div className="content-taxonomy-fields"><label><span>{t("contentTaxonomy.name")}</span><input onChange={(event) => patchEdit(topic.id, { name: event.target.value })} value={edit.name} /></label><label><span>{t("contentTaxonomy.parent")}</span><select onChange={(event) => patchEdit(topic.id, { parentId: event.target.value })} value={edit.parentId}><option value="">{t("contentTaxonomy.noParent")}</option>{rootTopics.filter((parent) => parent.id !== topic.id).map((parent) => <option key={parent.id} value={parent.id}>{parent.name}</option>)}</select></label><label className="is-order"><span>{t("contentTaxonomy.order")}</span><input min="0" onChange={(event) => patchEdit(topic.id, { sortOrder: event.target.value })} type="number" value={edit.sortOrder} /></label><label className="is-wide"><span>{t("contentTaxonomy.keywords")}</span><input onChange={(event) => patchEdit(topic.id, { keywords: event.target.value })} value={edit.keywords} /></label><label className="is-wide"><span>{t("contentTaxonomy.description")}</span><input onChange={(event) => patchEdit(topic.id, { description: event.target.value })} value={edit.description} /></label></div><footer><small>{topic.keywords_json?.length ?? 0} {t("contentTaxonomy.keywordCount")}</small><AsyncButton disabled={!changed || !edit.name.trim()} pending={busy === `save-${topic.id}`} onClick={() => void saveTopic(topic)}>{t("common.save")}</AsyncButton></footer></article>;
    })}</section>}
  </section>;
}
