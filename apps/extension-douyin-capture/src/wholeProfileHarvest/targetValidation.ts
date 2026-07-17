import type { ModalWholeProfileCandidateClassification, ModalWholeProfileCard } from "../modalWholeProfileTest.js";
import type { WholeProfileHarvestRejectedCandidate, WholeProfileHarvestTargetDetail } from "./state.js";

export type WholeProfileTargetValidationResult = {
  targets: string[];
  target_details: WholeProfileHarvestTargetDetail[];
  rejected_candidates_sample: WholeProfileHarvestRejectedCandidate[];
  raw_candidate_count: number;
  accepted_target_count: number;
  rejected_target_count: number;
};

export function validateWholeProfileTargets(cards: ModalWholeProfileCard[], classifications: ModalWholeProfileCandidateClassification[] = [], profileUrl: string | null = null): WholeProfileTargetValidationResult {
  const seen = new Set<string>();
  const targets: string[] = [];
  const targetDetails: WholeProfileHarvestTargetDetail[] = [];
  const rejected: WholeProfileHarvestRejectedCandidate[] = [];

  for (const card of cards) {
    const awemeId = String(card.aweme_id || "").trim();
    if (!isValidAwemeTarget(awemeId)) {
      rejected.push({ candidate_id: awemeId || "missing", reason: "invalid_aweme_id", source: card.extraction_source });
      continue;
    }
    if (seen.has(awemeId)) {
      rejected.push({ candidate_id: awemeId, reason: "duplicate", source: card.extraction_source });
      continue;
    }
    seen.add(awemeId);
    targets.push(awemeId);
    targetDetails.push({
      index: targets.length,
      aweme_id: awemeId,
      source_url: card.source_url ?? null,
      profile_url: profileUrl,
      thumbnail_url: card.thumbnail_url ?? null,
      title: card.title ?? null,
      caption: card.caption ?? null,
      text_sample: card.text_sample ?? null,
      posted_text: card.posted_text ?? null,
      posted_at: card.posted_at ?? null,
      duration_text: card.duration_text ?? null,
      duration_seconds: typeof card.duration_seconds === "number" ? card.duration_seconds : null,
      view_text: card.view_text ?? null,
      view_count: typeof card.view_count === "number" ? card.view_count : null,
      candidate_validation: {
        status: "accepted",
        source: card.extraction_source === "modal_link" || card.extraction_source === "data_attr" || card.extraction_source === "card_context_regex" ? card.extraction_source : "video_link",
        reason: null,
        source_url: card.source_url ?? null,
        card_context: true
      },
      metadata_completeness: {
        has_profile_identity: Boolean(profileUrl),
        has_thumbnail: Boolean(card.thumbnail_url),
        has_title_or_caption: Boolean(card.title ?? card.caption ?? card.text_sample),
        has_posted_text: Boolean(card.posted_text ?? card.posted_at),
        has_duration: Boolean(card.duration_text ?? card.duration_seconds),
        has_view_count: Boolean(card.view_count ?? card.view_text),
        has_detail_metrics: false
      },
      capture_status: "unknown",
      backend_item: null,
      extraction_source: card.extraction_source,
      profile_card_evidence: card.raw_profile_card
    });
  }

  for (const item of classifications) {
    if (item.status === "rejected") rejected.push({ candidate_id: item.candidate_id, reason: item.reason, source: item.source });
  }

  return {
    targets,
    target_details: targetDetails,
    rejected_candidates_sample: rejected.slice(0, 10),
    raw_candidate_count: Math.max(cards.length, classifications.length),
    accepted_target_count: targets.length,
    rejected_target_count: rejected.length
  };
}

export function isValidAwemeTarget(value: string): boolean {
  return /^\d{16,22}$/.test(value) && !/^1[0-9]{9}$/.test(value);
}
