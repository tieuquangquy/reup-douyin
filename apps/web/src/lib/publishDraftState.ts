import type { EditablePublishDraft, HashtagDraftItem, PublishDraft, PublishTarget } from "../types/publish-draft";

export function buildEditablePublishDraft(draft: PublishDraft): EditablePublishDraft {
  return {
    id: draft.id,
    targetPlatform: draft.target_platform,
    platformAccountRef: draft.platform_account_ref ?? "",
    title: draft.title ?? "",
    caption: draft.caption ?? "",
    ctaText: draft.cta_text ?? "",
    hashtags: normalizeHashtags(draft.hashtags_json ?? []),
    languageCode: draft.language_code ?? "vi",
    platformNotes: draft.platform_notes ?? "",
    schedulingNotes: draft.scheduling_notes ?? "",
    notes: draft.notes ?? "",
    plannedPublishAt: toDatetimeLocalValue(draft.planned_publish_at),
    timezone: draft.timezone ?? "Asia/Bangkok"
  };
}

export function toPublishDraftUpdatePayload(editable: EditablePublishDraft) {
  return {
    target_platform: editable.targetPlatform,
    platform_account_ref: editable.platformAccountRef || null,
    title: editable.title,
    caption: editable.caption,
    cta_text: editable.ctaText,
    hashtags: editable.hashtags,
    language_code: editable.languageCode,
    platform_notes: editable.platformNotes || null,
    scheduling_notes: editable.schedulingNotes || null,
    notes: editable.notes || null
  };
}

export function buildPostPreview(editable: EditablePublishDraft): string {
  const hashtags = editable.hashtags.map((item) => `#${cleanTag(item.tag)}`).filter((tag) => tag.length > 1);
  return [editable.caption.trim(), editable.ctaText.trim(), hashtags.join(" ")].filter(Boolean).join("\n\n");
}

export function validatePublishDraft(editable: EditablePublishDraft, target: PublishTarget | null): string[] {
  const errors: string[] = [];
  if (!editable.targetPlatform) errors.push("Target platform is required.");
  if (!editable.caption.trim()) errors.push("Caption is required.");
  if (!editable.ctaText.trim()) errors.push("CTA is required.");
  if (editable.hashtags.length === 0) errors.push("At least one hashtag is required.");
  if (target && editable.hashtags.length > target.hashtag_limit) errors.push(`Hashtag limit for ${target.label} is ${target.hashtag_limit}.`);
  if (target && buildPostPreview(editable).length > target.caption_max_length) errors.push(`Post text exceeds ${target.label} caption limit.`);
  return errors;
}

export function addHashtag(editable: EditablePublishDraft, rawTag: string): EditablePublishDraft {
  const tag = cleanTag(rawTag);
  if (!tag || editable.hashtags.some((item) => cleanTag(item.tag) === tag)) return editable;
  return { ...editable, hashtags: [...editable.hashtags, { tag, source: "operator" }] };
}

export function removeHashtag(editable: EditablePublishDraft, tag: string): EditablePublishDraft {
  const clean = cleanTag(tag);
  return { ...editable, hashtags: editable.hashtags.filter((item) => cleanTag(item.tag) !== clean) };
}

export function hasDraftChanges(current: EditablePublishDraft | null, saved: EditablePublishDraft | null): boolean {
  return JSON.stringify(current) !== JSON.stringify(saved);
}

export function schedulePayload(editable: EditablePublishDraft) {
  return {
    planned_publish_at: new Date(editable.plannedPublishAt).toISOString(),
    timezone: editable.timezone || "Asia/Bangkok",
    scheduling_notes: editable.schedulingNotes || null
  };
}

function normalizeHashtags(items: HashtagDraftItem[]): HashtagDraftItem[] {
  return items
    .map((item) => ({ tag: cleanTag(item.tag), source: item.source || "unknown" }))
    .filter((item) => item.tag.length > 0);
}

function cleanTag(value: string): string {
  return value.replace(/^#/, "").trim().replace(/\s+/g, "");
}

function toDatetimeLocalValue(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 16);
}
