import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  DEFAULT_FILTERS,
  visibleCandidates
} from "../lib/reviewBoardState";
import type { Candidate } from "../types/review-board";

const candidateA = makeCandidate("a", 88, "APPROVED", "2026-04-10T00:00:00Z", 120000, "street food");
const candidateB = makeCandidate("b", 62, "SHORTLISTED", "2026-04-12T00:00:00Z", 45000, "travel vlog");
const internalScoreOnly = makeCandidate("internal", 99, "NEW", "2026-04-11T00:00:00Z", 0, "internal only", null);

const sortedByScore = visibleCandidates([candidateB, candidateA, internalScoreOnly], DEFAULT_FILTERS);
assert.equal(sortedByScore[0].id, "a");
assert.equal(DEFAULT_FILTERS.status, "SHORTLISTED", "Review Board must default to the Shortlisted pipeline tab");

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrcDir = resolve(testDir, "..");
const reviewPageSource = readFileSync(resolve(webSrcDir, "components/review-board/ReviewBoardPage.tsx"), "utf8");
const reviewTileActionsSource = readFileSync(resolve(webSrcDir, "components/review-board/ReviewBoardTileActions.tsx"), "utf8");
const reviewBoardSource = reviewPageSource + reviewTileActionsSource;
const apiSource = readFileSync(resolve(webSrcDir, "lib/api.ts"), "utf8");
const globalStylesSource = readFileSync(resolve(webSrcDir, "app/globals.css"), "utf8");

assert.match(reviewPageSource, /capture-inbox-review-workspace/, "22F-6A must use Capture Inbox review workspace layout");
assert.match(reviewPageSource, /capture-inbox-review-main/, "22F-6A must use Capture Inbox main gallery column");
assert.doesNotMatch(reviewPageSource, /capture-inbox-review-side/, "Review Board must not reserve sticky right inspector column");
assert.match(reviewPageSource, /WorkItemDetailsDrawer/, "Review Board must open details in WorkItemDetailsDrawer");
assert.match(reviewPageSource, /capture-inbox-status-strip/, "22F-6A must use Capture Inbox status strip");
assert.match(reviewPageSource, /capture-inbox-status-pill/, "22F-6A must use Capture Inbox status pills");
assert.match(reviewPageSource, /review-board-command-deck/, "Review Board must use unified command deck");
assert.doesNotMatch(reviewPageSource, /review-board-studio-toolbar/, "Review Board must not use separate filter panel");
assert.doesNotMatch(reviewPageSource, /capture-inbox-gallery-summary/, "Review Board must not repeat hero counts in gallery summary");
assert.match(reviewPageSource, /review-board-command-deck-bulk/, "Review Board bulk actions must live inside command deck");
assert.match(reviewPageSource, /capture-inbox-command-bar/, "22F-6A must use Capture Inbox bulk command bar");
assert.match(reviewPageSource, /review-board-bulk-command-bar/, "22F-6B must use compact bulk command bar");
assert.match(reviewPageSource, /capture-inbox-media-tile/, "22F-6A must render candidate tiles like Capture Inbox");
assert.match(reviewPageSource, /capture-inbox-media-tile-grid/, "22F-6A must render tile gallery grid");
assert.match(reviewPageSource, /Select visible/, "Bulk bar must expose select visible");
assert.match(reviewBoardSource, /Approve & send/, "Bulk bar must expose approve and send fast path");
assert.match(reviewPageSource, /title="Approve selected candidates without queueing"/, "Bulk bar must expose approve-only action");
assert.match(reviewPageSource, /bulkApproveSelected/, "Approve must run without confirmation dialog");
assert.match(reviewPageSource, /bulkLaterSelected/, "Later must run without confirmation dialog");
assert.match(reviewPageSource, /Reject selected candidates/, "Reject must use confirmation dialog");
assert.match(reviewPageSource, /Remove from board/, "Bulk bar must expose remove from board action");
assert.match(reviewPageSource, /review-board-bulk-dialog-backdrop/, "Bulk dialog must use viewport backdrop");
assert.match(reviewPageSource, /<\/div>\s*<ReviewRightInspector[\s\S]*<ReviewBulkDialog/, "Bulk dialog must render after workspace drawer, not inside side column");
assert.match(reviewPageSource, /selectedIds/, "Studio must track bulk selection");
assert.match(reviewPageSource, /toggleSelection/, "Bulk select must use shared selection helper");
assert.match(reviewPageSource, /pickBestBenchCandidateId/, "Compare finalists must use scoring helper");
assert.match(reviewPageSource, /formatReviewEstimatedViews/, "Tiles must derive estimated views through shared helper");
assert.match(reviewPageSource, /fetchCandidateDetail/, "Inspector must hydrate via GET /candidates/:id");
assert.match(reviewPageSource, /function closeInspector/, "Review Board must centralize inspector close behavior");
assert.match(reviewPageSource, /setActiveCandidateId\(null\)/, "Close details must clear the active candidate selection");
assert.match(reviewPageSource, /onClose=\{closeInspector\}/, "Inspector close button must use shared close handler");
assert.match(reviewPageSource, /data-review-board-ui-version=\{UI_VERSION\}/, "Review Board must expose UI version marker");
assert.match(reviewPageSource, /22F-7R/, "Review Board UI version must be 22F-7R");
assert.match(reviewPageSource, /useSearchParams/, "Review Board must read deep-link candidate query");
assert.match(reviewPageSource, /searchParams\.get\("candidate"\)/, "Review Board must open candidate from ?candidate= link");
assert.match(reviewPageSource, /serverSearchActive/, "Search must trust API results without client re-filter");
assert.match(apiSource, /params\.set\("search", search\)/, "fetchCandidates must send search to API");
assert.match(reviewPageSource, /Loaded <strong>\{loadedCount\.toLocaleString\("en-US"\)\}<\/strong> \/ <strong>\{totalCount\.toLocaleString\("en-US"\)\}<\/strong>/, "Review Board must show loaded vs total counts");
assert.match(reviewPageSource, /OffsetLoadMoreFooter/, "Review Board must use shared offset load-more footer");
assert.match(reviewPageSource, /loadMoreCandidates/, "Review Board must support paginated candidate loading");
assert.match(apiSource, /options\?: \{ limit\?: number; offset\?: number \}/, "fetchCandidates must accept pagination options");
assert.match(reviewPageSource, /reup-queue-hero-stats/, "Status filters must use Reup Queue hero stats row");
assert.match(reviewPageSource, /reup-queue-hero-stat/, "Status filters must reuse Reup Queue hero stat pills");
assert.match(reviewPageSource, /reviewBoardFilterTone/, "Status filters must use count-aware tone mapping");
assert.doesNotMatch(reviewPageSource, /review-board-soft-chip/, "Review Board must not use custom soft chip styles");
assert.doesNotMatch(reviewPageSource, /review-board-pipeline-segmented/, "Review Board must not use pipeline segmented control");
assert.match(reviewPageSource, /review-board-media-tile/, "Tiles must use review-board overlay styling scope");
assert.match(reviewPageSource, /is-bulk-selected/, "Bulk selection must highlight tile border");
assert.match(reviewPageSource, /WorkMediaTileOverlay/, "Tiles must use shared Work overlay labels");
assert.match(reviewPageSource, /getOperatorTileScoreBadge/, "Tiles must use shared score badge authority");
assert.match(reviewPageSource, /reviewBoardStatusTone/, "Review Board must map SHORTLISTED to visible status tone");
assert.doesNotMatch(reviewPageSource, /review-board-decision-focus-compact|review-board-queue-table|review-board-gallery-shell|review-board-decision-layout/, "22F-6A must remove decision-console layout");
assert.match(reviewPageSource, /formatExactEngagementMetric\(metadata\.likeCount, metadata\.likeCountText\)/, "Review Board tiles must render exact engagement metrics");
assert.match(reviewBoardSource, /review-board-queue-pair/, "Approved in-queue tiles must use queue action pair layout");
assert.match(reviewBoardSource, /ReviewBoardTileActions/, "Review Board tiles must use dedicated tile action component");
assert.match(reviewBoardSource, /review-board-tile-action-bar/, "Review Board tiles must use structured action bar layout");
assert.match(reviewBoardSource, /View details/, "Review Board tiles must expose tertiary details action");
assert.match(reviewBoardSource, /is-promoted-open/, "Approved in-queue tiles must use promoted-open primary action");
assert.match(reviewBoardSource, /is-promoted-details/, "Approved in-queue tiles must use promoted-details secondary action");
assert.match(reviewBoardSource, /Open queue/, "In-queue primary action must use compact Open queue label");
assert.doesNotMatch(reviewBoardSource, /review-board-tile-action-span" href="\/selection\/reup-queue"/, "In-queue tiles must not use full-width span link layout");
assert.match(reviewPageSource, /reviewCandidateDisplayScore\(candidate\)/, "Visible score must use reup_score adapter");
assert.match(reviewPageSource, /buildCapturedItemFromReviewCandidate/, "Review Board score badge must use shared capture scoring shape");
assert.match(reviewPageSource, /reupScoreBadgeLevelForCaptureItem/, "Review Board score badge must use shared completeness-aware levels");
assert.match(reviewPageSource, /getOperatorTileScoreBadge\(buildCapturedItemFromReviewCandidate\(candidate\)\)/, "Review Board tiles must use shared score badge authority");
assert.doesNotMatch(reviewPageSource, /function formatScore/, "Review Board must not keep local score badge formatters");
assert.match(apiSource, /params\.set\("view", "summary"\)/, "Review Board API helper must request summary list view");
assert.match(globalStylesSource, /Phase 22F-7E: unified command deck/, "Styles must document 22F-7E command deck");
assert.match(globalStylesSource, /22F-7N comfortable scale/, "Styles must document 22F-7N comfortable scale");
assert.match(globalStylesSource, /\.review-board-tile-action-bar[\s\S]*\.review-board-tile-btn\.is-primary/, "Review Board tile actions must define dedicated primary button styles");
assert.match(globalStylesSource, /\.review-board-tile-btn\.is-ghost/, "Review Board tile actions must define tertiary ghost details button");

console.log("review-board state tests passed");

function makeCandidate(
  id: string,
  score: number,
  status: Candidate["status"],
  postedAt: string,
  views: number,
  caption: string,
  reupScore: number | null = score
): Candidate {
  return {
    id,
    source_video_id: `video-${id}`,
    status,
    score,
    reup_score: reupScore,
    estimated_views_mid: views || null,
    like_count: views ? Math.max(50, Math.round(views / 80)) : null,
    comment_count: views ? Math.max(5, Math.round(views / 800)) : null,
    share_count: views ? Math.max(3, Math.round(views / 400)) : null,
    duration_seconds: 42,
    thumbnail_url: "https://cdn.example.test/thumb.jpg",
    posted_display: "2026-04-10",
    score_version: "REUP_SCORE_V1",
    score_label: score >= 75 ? "hot" : "usable",
    score_breakdown_json: null,
    score_reason: "strong like rate",
    preset_name: "viral_discovery",
    filter_config_json: {},
    inclusion_reasons_json: ["strong like rate"],
    exclusion_reasons_json: [],
    warnings_json: [],
    evaluated_at: postedAt,
    priority: Math.round(score),
    metadata_json: {},
    created_at: postedAt,
    updated_at: postedAt,
    source_video: {
      id: `video-${id}`,
      source_profile_id: "profile-1",
      source_video_external_id: `external-${id}`,
      source_url: `https://example.test/${id}`,
      caption,
      posted_at: postedAt,
      duration_seconds: 30,
      metadata_json: { thumbnail_url: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3", reup_score: reupScore, estimated_views_mid: views || null }
    }
  };
}
