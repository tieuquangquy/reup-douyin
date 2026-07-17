/**
 * Hybrid pre-skip must not treat stub/partial Capture Inbox rows as fully collected.
 * Production: verify returned any matching aweme_id, so legacy RAW rows with no
 * metrics blocked re-hydration forever while the UI showed "Metadata complete"
 * without source links or engagement evidence.
 */
export function isBackendVerifyItemFullyCollectedForHybridPreSkip(item: Record<string, unknown>): boolean {
  const awemeId = typeof item.aweme_id === "string"
    ? item.aweme_id.trim()
    : typeof item.source_video_external_id === "string"
      ? item.source_video_external_id.trim()
      : "";
  if (!awemeId) return false;

  if (item.has_all_core_metadata === true) return true;

  const metadataStatus = typeof item.metadata_status === "string"
    ? item.metadata_status.trim().toLowerCase()
    : null;

  if (metadataStatus) {
    if (metadataStatus !== "complete") return false;
    const sourceUrl = typeof item.source_url === "string" ? item.source_url.trim() : "";
    const shareUrl = typeof item.share_url === "string" ? item.share_url.trim() : "";
    if (!sourceUrl || !shareUrl) return false;
    return item.has_likes === true
      && item.has_duration === true
      && item.has_posted === true
      && item.has_thumbnail === true;
  }

  // Legacy verify mocks / minimal payloads with only aweme_id — preserve idempotency tests.
  const hasMetadataSignals = "metadata_status" in item
    || "has_all_core_metadata" in item
    || "source_url" in item
    || "like_count" in item
    || "has_likes" in item;
  return !hasMetadataSignals;
}
