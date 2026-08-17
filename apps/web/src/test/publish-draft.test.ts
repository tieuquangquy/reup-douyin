import assert from "node:assert/strict";
import {
  addHashtag,
  buildEditablePublishDraft,
  buildPostPreview,
  hasDraftChanges,
  isCompletePlannedPublishAt,
  joinPlannedPublishAt,
  removeHashtag,
  schedulePayload,
  splitPlannedPublishAt,
  toPublishDraftUpdatePayload,
  validatePublishDraft
} from "../lib/publishDraftState";
import type { PublishDraft, PublishTarget } from "../types/publish-draft";

const draft = makeDraft();
const editable = buildEditablePublishDraft(draft);
assert.equal(editable.caption, "Video moi da Viet hoa");
assert.equal(editable.hashtags.length, 2);

const withTag = addHashtag(editable, "#xuhuong");
assert.equal(withTag.hashtags.some((item) => item.tag === "xuhuong"), true);
assert.equal(addHashtag(withTag, "xuhuong").hashtags.length, withTag.hashtags.length);

const withoutTag = removeHashtag(withTag, "vietsub");
assert.equal(withoutTag.hashtags.some((item) => item.tag === "vietsub"), false);

const preview = buildPostPreview(withTag);
assert.equal(preview.includes("#xuhuong"), true);
assert.equal(preview.includes("Xem them video moi"), true);

const target: PublishTarget = {
  platform: "TIKTOK",
  label: "TikTok",
  caption_max_length: 2200,
  hashtag_limit: 12,
  supports_scheduling: true,
  account_ref_required: false
};
assert.deepEqual(validatePublishDraft(withTag, target), []);
assert.equal(validatePublishDraft({ ...withTag, caption: "" }, target).includes("Caption is required."), true);

assert.equal(hasDraftChanges(withTag, editable), true);
assert.equal(toPublishDraftUpdatePayload(withTag).target_platform, "TIKTOK");

const scheduled = { ...withTag, plannedPublishAt: "2026-04-18T09:30", timezone: "Asia/Bangkok" };
assert.equal(schedulePayload(scheduled).timezone, "Asia/Bangkok");
assert.deepEqual(splitPlannedPublishAt("2026-04-18T09:30"), { date: "2026-04-18", time: "09:30" });
assert.equal(joinPlannedPublishAt("2026-04-18", "09:30"), "2026-04-18T09:30");
assert.equal(joinPlannedPublishAt("2026-04-18", ""), "2026-04-18T09:00");
assert.equal(joinPlannedPublishAt("", "09:30"), "");
assert.equal(isCompletePlannedPublishAt("2026-04-18T09:30"), true);
assert.equal(isCompletePlannedPublishAt("2026-04-18"), false);

console.log("publish-draft state tests passed");

function makeDraft(): PublishDraft {
  return {
    id: "draft-1",
    workspace_id: "workspace-1",
    source_video_id: "video-1",
    render_output_id: "render-1",
    target_platform: "TIKTOK",
    platform_account_ref: null,
    version: 1,
    status: "DRAFT",
    title: "Video title",
    caption: "Video moi da Viet hoa",
    cta_text: "Xem them video moi",
    language_code: "vi",
    hashtags_json: [
      { tag: "vietsub", source: "default" },
      { tag: "shortvideo", source: "default" }
    ],
    caption_draft_json: {},
    cta_draft_json: {},
    schedule_json: null,
    planned_publish_at: null,
    timezone: null,
    scheduled_at: null,
    ready_at: null,
    generation_source: "deterministic_v1",
    platform_payload_json: {},
    metadata_json: {},
    platform_notes: null,
    scheduling_notes: null,
    notes: null,
    error_message: null,
    canonical_publish_attempt_id: null,
    latest_publish_attempt_id: null,
    current_publication_status: "UNKNOWN",
    current_external_publish_id: null,
    current_external_permalink: null,
    published_at: null,
    last_publish_synced_at: null,
    publication_summary_json: null,
    assigned_platform_account_id: null,
    assignment_status: "UNASSIGNED",
    assigned_at: null,
    assigned_reason: null,
    assigned_by: null,
    assignment_metadata_json: null,
    created_at: "2026-04-17T00:00:00Z",
    updated_at: "2026-04-17T00:00:00Z"
  };
}
