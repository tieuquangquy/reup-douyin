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
const workStudioChromeSource = readFileSync(resolve(webSrcDir, "components/shared/WorkStudioChrome.tsx"), "utf8");
const reviewBoardSource = reviewPageSource + reviewTileActionsSource;
const apiSource = readFileSync(resolve(webSrcDir, "lib/api.ts"), "utf8");
const globalStylesSource = readFileSync(resolve(webSrcDir, "app/globals.css"), "utf8");

assert.match(reviewPageSource, /capture-inbox-review-workspace/, "22F-6A must use Capture Inbox review workspace layout");
assert.match(reviewPageSource, /capture-inbox-review-main/, "22F-6A must use Capture Inbox main gallery column");
assert.doesNotMatch(reviewPageSource, /capture-inbox-review-side/, "Review Board must not reserve sticky right inspector column");
assert.match(reviewPageSource, /WorkItemDetailsDrawer/, "Review Board must open details in WorkItemDetailsDrawer");
assert.match(reviewPageSource, /capture-inbox-status-flow/, "Review Board must use Capture Inbox status-flow grammar");
assert.match(reviewPageSource, /capture-inbox-stat-card/, "Review Board must use Capture Inbox status cards");
assert.match(reviewPageSource, /review-board-command-deck/, "Review Board must use unified command deck");
assert.match(reviewPageSource, /WorkStudioDeck/, "Review Board must use shared Work studio deck chrome");
assert.match(globalStylesSource, /\.review-board-command-deck\s*\{[^}]*position: static;/, "Review studio deck must scroll with the page instead of sticking to the viewport");
assert.doesNotMatch(globalStylesSource, /\.review-board-command-deck\s*\{[^}]*position:\s*sticky;/, "No later duplicate rule may make the Review studio deck sticky again");
assert.match(reviewPageSource, /capture-inbox-hero-action-rail review-board-hero-action-rail/, "Review Board shortcuts must use the Capture Inbox action rail");
assert.match(globalStylesSource, /\.review-board-hero-action-rail\s*\{[^}]*border: 1px solid color-mix\(in srgb, var\(--accent\) 24%, var\(--line\)\);[^}]*box-shadow: none;/, "Review Board action rail must use a subtle accent border without a floating shadow");
assert.match(globalStylesSource, /\.review-board-hero-action-rail \.capture-inbox-hero-action-rail__item\s*\{[^}]*box-shadow: none;/, "Open Reup Queue itself must not retain any button shadow");
assert.match(globalStylesSource, /\.review-board-command-deck \.work-studio-deck__header\.capture-inbox-command-deck-top\s*\{[^}]*padding: 0\.34rem var\(--capture-deck-pad-x\);/, "Review studio header must use compact balanced vertical padding");
assert.match(globalStylesSource, /\.review-board-hero-action-rail \.capture-inbox-hero-action-rail__item\s*\{[^}]*min-height: 2rem;/, "Open Reup Queue must use a compact but usable height");
assert.match(globalStylesSource, /\.review-board-hero-action-rail \.capture-inbox-hero-action-rail__icon\s*\{[^}]*height: 1\.5rem;[^}]*width: 1\.5rem;/, "Review header action icon must fit the compact rail");
assert.match(reviewPageSource, /kind="open"[\s\S]*Open Reup Queue/, "Open Reup Queue must use the Capture Inbox icon-and-label pattern");
assert.doesNotMatch(reviewPageSource, /capture-inbox-hero-action-rail__divider/, "A single Review header shortcut must not render an orphan divider");
assert.match(reviewPageSource, /review-board-gallery-select-visible[\s\S]*kind="select-visible"[\s\S]*Select visible/, "Select visible must move to the gallery toolbar with its leading icon");
assert.doesNotMatch(reviewPageSource, /shortlisted · Loaded/, "Review header must not repeat counts already shown by status cards and gallery");
assert.match(reviewPageSource, /ReviewStatusFlow/, "Review Board must present status filters in a Capture Inbox-style lane");
assert.match(reviewPageSource, /useTransition/, "Review status switches must use a non-blocking React transition");
assert.match(reviewPageSource, /startStatusTransition/, "Status tab changes must enter the transition boundary");
assert.match(reviewPageSource, /ReviewGalleryPreloading/, "Review Board must provide a dedicated gallery preloading surface");
assert.match(reviewPageSource, /isStatusPending \? \([\s\S]*<ReviewGalleryPreloading/, "Pending status changes must replace heavy tiles with preloading UI");
assert.match(reviewPageSource, /displayVisible\.length > 0 \|\| isStatusPending/, "Preloading must remain visible when switching away from an empty status");
assert.match(reviewPageSource, /<\/>\s*\)\}\s*\{hasMoreCandidates \|\| totalCount > 0 \? \(/, "Auto-load sentinel must remain mounted outside the preloading tile branch");
assert.match(reviewPageSource, /disabled=\{mutating \|\| isStatusPending\}/, "Auto-load must pause safely while status tiles transition");
assert.match(globalStylesSource, /\.review-board-media-tile\s*\{[^}]*content-visibility: auto;[^}]*contain-intrinsic-size: 510px;/, "Offscreen Review tiles must defer browser layout and paint");
assert.match(globalStylesSource, /\.review-board-gallery-preloading\s*\{[^}]*min-height: 510px;/, "Preloading UI must reserve a stable gallery height");
assert.match(apiSource, /statusCounts: payload\.status_counts/, "Candidate API client must expose backend status counts");
assert.match(reviewPageSource, /setStatusCounts\(nextStatusCounts\)/, "Review Board must store authoritative backend status counts");
assert.match(reviewPageSource, /buildSummaryFromStatusCounts\(statusCounts\)/, "Pipeline cards must use database status totals instead of the active tab total");
assert.match(reviewPageSource, /Object\.values\(statusCounts\)\.reduce/, "The All Pipeline card must remain the sum of every status while a status tab is active");
assert.doesNotMatch(reviewPageSource, /buildSummary\(statusSummaryBase\)/, "Pipeline totals must not be derived from the paginated candidate array");
assert.doesNotMatch(reviewPageSource, /resolvedTotalCount/, "Review pagination must never shrink the backend total to a stalled loaded count");
assert.match(reviewPageSource, /async function updateCandidateStatuses[\s\S]*?await loadData\("refresh"\);/, "Status mutations must refresh authoritative Pipeline counts");
assert.match(reviewPageSource, /async function bulkRemoveSelected[\s\S]*?await loadData\("refresh"\);/, "Candidate removal must refresh authoritative Pipeline counts");
assert.match(
  reviewPageSource,
  /async function approveAndSendCandidatesToReupQueue[\s\S]*?await loadData\("refresh"\);/,
  "Approve & send must refresh authoritative Pipeline counts after status changes"
);
assert.match(reviewPageSource, /capture-inbox-status-flow__lane is-pipeline/, "Review Board must group all statuses in one pipeline lane");
assert.doesNotMatch(reviewPageSource, /capture-inbox-status-flow__lane is-attention/, "Review Board must not place Rejected on a second row");
assert.match(reviewPageSource, /REVIEW_STATUS_FILTERS\.map\(\(entry\) => renderCard\(entry, entry\.key === "REJECTED" \? "attention" : "pipeline"\)\)/, "Review Board must render all six statuses in one ordered track");
assert.match(globalStylesSource, /\.review-board-status-flow \.capture-inbox-status-flow__track\s*\{[^}]*grid-template-columns: repeat\(6, minmax\(0, 1fr\)\)/, "Review Board desktop statuses must share one horizontal row");
assert.match(globalStylesSource, /\.review-board-status-flow\s*\{[^}]*padding: 0\.7rem var\(--capture-deck-pad-x\) 0\.75rem;/, "Review status flow must breathe below the studio header");
assert.match(globalStylesSource, /\.review-board-status-flow \.capture-inbox-status-flow__lane\s*\{[^}]*gap: 0\.65rem;/, "Pipeline heading and status cards must not touch");
assert.match(reviewPageSource, /REVIEW_STATUS_STAT_BAR_PATTERNS/, "Review Board must define a distinct five-bar pattern for every status");
assert.match(reviewPageSource, /function ReviewStatusStatBars/, "Review Board must render the same compact bar visualization as Capture Inbox");
assert.match(reviewPageSource, /<ReviewStatusStatBars[\s\S]*status=\{entry\.key\}/, "Every Review status card must include its matching bar icon");
assert.match(reviewPageSource, /review-board-filter-deck/, "Review Board must separate filters into a Capture Inbox-style filter deck");
assert.match(reviewPageSource, /WorkBulkActionBar/, "Review Board bulk decisions must use shared Work bulk chrome");
assert.match(reviewPageSource, /WorkGalleryHeader/, "Review Board gallery must use shared Capture-style heading hierarchy");
assert.match(reviewPageSource, /WorkGalleryEmptyState/, "Review Board loading and empty branches must use shared Work gallery surfaces");
assert.match(reviewPageSource, /className="review-board-empty-capture-link"[\s\S]*kind="open"[\s\S]*Open Capture Inbox/, "Empty Review Board CTA must render a leading icon with its text");
assert.match(globalStylesSource, /\.review-board-empty-capture-link\s*\{[^}]*display: inline-flex;[^}]*gap: 0\.4rem;/, "Open Capture Inbox CTA must align its icon and text");
assert.match(workStudioChromeSource, /className\?: string;/, "Shared Work empty state must accept a page-specific layout class");
assert.match(reviewPageSource, /<WorkGalleryEmptyState[\s\S]*?className="review-board-gallery-empty"/, "Review Board empty states must opt into the balanced centered layout");
assert.match(
  globalStylesSource,
  /\.review-board-gallery-empty \.capture-inbox-gallery-empty__card\s*\{[^}]*flex-direction: column;[^}]*justify-content: center;[^}]*min-height: 11rem;[^}]*text-align: center;/,
  "Review Board empty card must use a centered vertical hierarchy"
);
assert.match(
  globalStylesSource,
  /\.review-board-gallery-empty \.capture-inbox-gallery-empty__action\s*\{[^}]*margin-left: 0;[^}]*margin-top: 0\.25rem;/,
  "Review Board empty CTA must sit below the explanatory copy"
);
assert.match(reviewPageSource, /review-board-filter-control is-search[\s\S]*review-board-filter-search-icon[\s\S]*Search video ID/, "Review filters must present search as an icon-led control");
assert.match(reviewPageSource, /review-board-filter-control is-sort[\s\S]*Sort by[\s\S]*Reup Score/, "Review filters must give sorting a clear micro-label");
assert.match(reviewPageSource, /aria-expanded=\{scoreRangeOpen\}[\s\S]*Score range[\s\S]*Apply filters/, "Review filters must expose score range as a toggle before the primary apply action");
assert.match(reviewPageSource, /review-board-score-range__field[\s\S]*Minimum[\s\S]*Maximum/, "Expanded score controls must label both range boundaries");
assert.match(globalStylesSource, /\.review-board-filter-deck\s*\{[^}]*box-shadow: none;[^}]*padding: 0;/, "Redesigned Review filters must use flat compact deck chrome");
assert.match(globalStylesSource, /\.review-board-filter-control\s*\{[^}]*display: flex;[^}]*min-height: 2\.5rem;/, "Review filter fields must share one aligned control shell");
assert.match(globalStylesSource, /\.review-board-score-range__field\s*\{[^}]*align-items: center;[^}]*display: flex;[^}]*flex: 1 1 0;/, "Score labels and inputs must share one horizontal line and distribute the available width");
assert.match(globalStylesSource, /\.review-board-score-range \.review-board-deck-score\s*\{[^}]*flex: 1 1 auto;[^}]*width: auto;/, "Score inputs must expand to fill their range field");
assert.doesNotMatch(reviewPageSource, /review-board-studio-toolbar/, "Review Board must not use separate filter panel");
assert.doesNotMatch(reviewPageSource, /capture-inbox-gallery-summary/, "Review Board must not repeat hero counts in gallery summary");
assert.match(reviewPageSource, /review-board-command-deck-bulk/, "Review Board bulk actions must live inside command deck");
assert.match(reviewPageSource, /capture-inbox-command-bar/, "22F-6A must use Capture Inbox bulk command bar");
assert.match(reviewPageSource, /review-board-bulk-command-bar/, "22F-6B must use compact bulk command bar");
assert.match(reviewPageSource, /\{hasSelection \? \(\s*<WorkBulkActionBar/, "Review Board must hide the empty bulk bar until candidates are selected");
assert.doesNotMatch(reviewPageSource, /Select visible candidates to review them together/, "Review Board must not reserve an idle row for redundant selection guidance");
assert.match(reviewPageSource, /kind="clear-selection"[\s\S]*Clear/, "Active bulk bar must give Clear a leading icon");
assert.match(reviewPageSource, /kind="send"[\s\S]*Approve &amp; send/, "Active bulk primary action must use an icon-and-text hierarchy");
assert.match(globalStylesSource, /\.review-board-bulk-command-bar\.is-compact\.is-active\s*\{[^}]*grid-template-columns: minmax\(220px, 1fr\) auto;[^}]*box-shadow: none;/, "Active Review bulk bar must use a flat compact single-row layout");
assert.match(globalStylesSource, /\.review-board-bulk-command-bar\.is-compact\.is-active\s*\{[^}]*position: sticky;[^}]*top: 12px;[^}]*z-index: 8;/, "Active Review bulk actions must stick on scroll like Capture Inbox");
assert.match(reviewPageSource, /capture-inbox-media-tile/, "22F-6A must render candidate tiles like Capture Inbox");
assert.match(reviewPageSource, /capture-inbox-media-tile-grid/, "22F-6A must render tile gallery grid");
assert.match(reviewPageSource, /Select visible/, "Bulk bar must expose select visible");
assert.match(reviewBoardSource, /Approve & send/, "Bulk bar must expose approve and send fast path");
assert.match(
  reviewPageSource,
  /onApproveAndSend=\{|onApproveAndSend=\{\(candidate\)/,
  "Details drawer must receive Approve & send like tiles"
);
assert.match(reviewTileActionsSource, /Approve & send/, "Tile/inspector actions must expose Approve & send");
assert.doesNotMatch(
  reviewTileActionsSource,
  /if \(variant === "inspector" && !inReupQueue\)/,
  "Inspector must not use a stripped action set that drops Approve & send"
);
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
assert.match(reviewPageSource, /review-board-inspector-summary-card[\s\S]*review-board-inspector-media[\s\S]*thumbnailUrl/, "Review inspector must lead with a visual candidate summary");
assert.match(reviewPageSource, /review-board-inspector-metadata-grid[\s\S]*CaptureInboxFilterChipIcon/, "Review inspector metadata must use a compact icon-led grid");
assert.doesNotMatch(reviewPageSource, /<OpsMetadataList/, "Review inspector must not retain the sparse one-column metadata list");
assert.match(globalStylesSource, /\.review-board-inspector-metadata-grid\s*\{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/, "Review inspector metadata must use two balanced columns");
assert.match(globalStylesSource, /\.review-board-inspector-stat\s*\{[^}]*display: grid;[^}]*grid-template-columns: 2rem minmax\(0, 1fr\);/, "Each inspector metric must align its icon, label, and value");
assert.match(reviewPageSource, /function closeInspector/, "Review Board must centralize inspector close behavior");
assert.match(reviewPageSource, /setActiveCandidateId\(null\)/, "Close details must clear the active candidate selection");
assert.match(reviewPageSource, /onClose=\{closeInspector\}/, "Inspector close button must use shared close handler");
assert.match(reviewPageSource, /data-review-board-ui-version=\{UI_VERSION\}/, "Review Board must expose UI version marker");
assert.match(reviewPageSource, /22F-7R/, "Review Board UI version must be 22F-7R");
assert.match(reviewPageSource, /useSearchParams/, "Review Board must read deep-link candidate query");
assert.match(reviewPageSource, /searchParams\.get\("candidate"\)/, "Review Board must open candidate from ?candidate= link");
assert.match(reviewPageSource, /serverSearchActive/, "Search must trust API results without client re-filter");
assert.match(apiSource, /params\.set\("search", search\)/, "fetchCandidates must send search to API");
assert.match(apiSource, /export async function fetchCandidates[\s\S]{0,700}if \(filters\.status\) params\.set\("status", filters\.status\)/, "fetchCandidates must send the selected Review status to the API");
assert.match(reviewPageSource, /function selectReviewStatus[\s\S]*setAppliedFilters\(\(current\) => \(\{ \.\.\.current, status \}\)\)/, "Status tabs must update the server-applied candidate filter");
assert.match(reviewPageSource, /`\$\{displayVisible\.length\.toLocaleString\(\)\} shown · \$\{totalCount\.toLocaleString\(\)\} total`/, "Gallery must retain visible vs total counts outside the compact studio header");
assert.match(reviewPageSource, /OffsetLoadMoreFooter/, "Review Board must use shared offset load-more footer");
assert.match(reviewPageSource, /const footerCandidateNoun = effectiveStatus[\s\S]*toLocaleLowerCase\(\)[\s\S]*candidates/, "Review pager must describe the active status instead of calling it the entire board");
assert.match(reviewPageSource, /noun=\{footerCandidateNoun\}/, "Review pager must render its status-aware candidate noun");
assert.match(reviewPageSource, /loadMoreCandidates/, "Review Board must support paginated candidate loading");
assert.match(apiSource, /options\?: \{ limit\?: number; offset\?: number \}/, "fetchCandidates must accept pagination options");
assert.doesNotMatch(reviewPageSource, /reup-queue-hero-stats|reup-queue-hero-stat/, "Review Board must not borrow Reup Queue status chrome");
assert.match(reviewPageSource, /reviewBoardFilterTone/, "Status filters must use count-aware tone mapping");
assert.doesNotMatch(reviewPageSource, /review-board-soft-chip/, "Review Board must not use custom soft chip styles");
assert.doesNotMatch(reviewPageSource, /review-board-pipeline-segmented/, "Review Board must not use pipeline segmented control");
assert.match(reviewPageSource, /review-board-media-tile/, "Tiles must use review-board overlay styling scope");
assert.match(reviewPageSource, /is-bulk-selected/, "Bulk selection must highlight tile border");
assert.match(reviewPageSource, /WorkMediaTileOverlay/, "Tiles must use shared Work overlay labels");
assert.doesNotMatch(reviewPageSource, /review-board-tile-star|Star finalist|Unstar finalist/, "Review tiles must not show a duplicate finalist star beside the score badge");
assert.match(reviewPageSource, /useReviewCandidateTileScoreBadge/, "Tiles must use shared score badge authority");
assert.match(reviewPageSource, /reviewBoardStatusTone/, "Review Board must map SHORTLISTED to visible status tone");
assert.doesNotMatch(reviewPageSource, /review-board-decision-focus-compact|review-board-queue-table|review-board-gallery-shell|review-board-decision-layout/, "22F-6A must remove decision-console layout");
assert.match(reviewPageSource, /formatExactEngagementMetric\(metadata\.likeCount, metadata\.likeCountText\)/, "Review Board tiles must render exact engagement metrics");
assert.match(reviewPageSource, /capture-inbox-tile-meta-line/, "Review Board tiles must use the Capture Inbox duration and posted meta line");
assert.match(reviewPageSource, /capture-inbox-tile-perf-rail/, "Review Board tiles must use the Capture Inbox icon and value performance rail");
assert.match(reviewPageSource, /CaptureInboxFilterChipIcon/, "Review Board performance stats must use the same visual icon language as Capture Inbox");
assert.doesNotMatch(reviewPageSource, /capture-inbox-tile-quick-meta/, "Review Board tiles must not keep legacy metadata chips");
assert.doesNotMatch(reviewPageSource, /capture-inbox-tile-metrics/, "Review Board tiles must not keep the legacy metric-cell grid");
assert.match(globalStylesSource, /\.review-board-tile-action-bar\.is-queue-pair\.review-board-queue-pair\.is-promoted-pair\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\);/, "Approved in-queue tiles must use a full-width single-column action layout");
assert.match(globalStylesSource, /\.review-board-tile-action-bar\.is-queue-pair \.review-board-tile-btn\.is-primary\.is-promoted-open\s*\{[^}]*grid-column: 1 \/ -1;[^}]*width: 100%;/, "Open queue must span the full tile action width");
assert.match(reviewBoardSource, /ReviewBoardTileActions/, "Review Board tiles must use dedicated tile action component");
assert.match(reviewBoardSource, /review-board-tile-action-bar/, "Review Board tiles must use structured action bar layout");
assert.doesNotMatch(reviewTileActionsSource, /View details|Inspect candidate details|kind="details"/, "Review Board tiles must rely on the image or title instead of a redundant details button");
assert.match(reviewBoardSource, /is-promoted-open/, "Approved in-queue tiles must use promoted-open primary action");
assert.doesNotMatch(reviewBoardSource, /is-promoted-details/, "Approved in-queue tiles must not retain a redundant details action");
assert.match(reviewBoardSource, /Open queue/, "In-queue primary action must use compact Open queue label");
assert.doesNotMatch(reviewBoardSource, /review-board-tile-action-span" href="\/selection\/reup-queue"/, "In-queue tiles must not use full-width span link layout");
assert.match(reviewPageSource, /reviewCandidateDisplayScore\(candidate\)/, "Visible score must use reup_score adapter");
assert.match(reviewPageSource, /buildCapturedItemFromReviewCandidate/, "Review Board score badge must use shared capture scoring shape");
assert.match(reviewPageSource, /reupScoreBadgeLevelForCaptureItem/, "Review Board score badge must use shared completeness-aware levels");
assert.match(reviewPageSource, /useReviewCandidateTileScoreBadge\(candidate\)/, "Review Board tiles must use shared score badge authority");
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
