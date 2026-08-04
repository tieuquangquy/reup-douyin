import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  captureSessionOptionLabel,
  intakeDateRange,
  intakeFiltersActive,
  promotedCaptureSessions
} from "../lib/reviewBoardIntake";
import type { CaptureSession } from "../types/capture-inbox";

const webSrcDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiSource = readFileSync(resolve(webSrcDir, "lib/api.ts"), "utf8");
const reviewPageSource = readFileSync(resolve(webSrcDir, "components/review-board/ReviewBoardPage.tsx"), "utf8");
const rowSource = readFileSync(resolve(webSrcDir, "components/shared/IntakeFilterRow.tsx"), "utf8");

// Wednesday 15 July 2026, 14:32 local time.
const NOW = new Date(2026, 6, 15, 14, 32, 10, 500);

function session(overrides: Partial<CaptureSession> = {}): CaptureSession {
  return {
    id: "session-1",
    workspace_id: "workspace-1",
    capture_id: null,
    source_platform: "DOUYIN",
    capture_source: "extension",
    status: "PROMOTED",
    detected_page_type: null,
    page_url: null,
    page_title: null,
    submitted_profile_url: "https://www.douyin.com/user/abc",
    normalized_profile_identifier: "abc",
    visible_item_count: 0,
    captured_item_count: 90,
    normalized_item_count: 90,
    duplicate_item_count: 0,
    ready_item_count: 0,
    skipped_item_count: 0,
    promoted_item_count: 87,
    candidate_created_count: 87,
    failed_item_count: 0,
    started_at: null,
    finished_at: null,
    diagnostics_json: null,
    metadata_json: null,
    raw_summary_json: null,
    result_summary_json: null,
    error_code: null,
    error_message: null,
    created_at: new Date(2026, 6, 15, 14, 32).toISOString(),
    updated_at: new Date(2026, 6, 15, 14, 32).toISOString(),
    ...overrides
  } as CaptureSession;
}

// Date chips must resolve to a half-open range so a clip is never counted in two buckets.
const today = intakeDateRange("today", NOW);
assert.equal(today.createdAfter, new Date(2026, 6, 15, 0, 0, 0, 0).toISOString(), "Today starts at local midnight");
assert.equal(today.createdBefore, new Date(2026, 6, 16, 0, 0, 0, 0).toISOString(), "Today ends at the next local midnight");

const week = intakeDateRange("7d", NOW);
assert.equal(week.createdAfter, new Date(2026, 6, 9, 0, 0, 0, 0).toISOString(), "7 days covers today plus the previous six days");
assert.equal(week.createdBefore, new Date(2026, 6, 16, 0, 0, 0, 0).toISOString());

const month = intakeDateRange("30d", NOW);
assert.equal(month.createdAfter, new Date(2026, 5, 16, 0, 0, 0, 0).toISOString(), "30 days covers today plus the previous 29 days");

const none = intakeDateRange("", NOW);
assert.equal(none.createdAfter, undefined, "No chip means no date bound");
assert.equal(none.createdBefore, undefined);

// A custom range must include the whole end day, not stop at its midnight.
const custom = intakeDateRange("custom", NOW, { from: "2026-07-01", to: "2026-07-10" });
assert.equal(custom.createdAfter, new Date(2026, 6, 1, 0, 0, 0, 0).toISOString());
assert.equal(
  custom.createdBefore,
  new Date(2026, 6, 11, 0, 0, 0, 0).toISOString(),
  "A custom end date must include clips added on that day"
);

const openEnded = intakeDateRange("custom", NOW, { from: "2026-07-01", to: "" });
assert.equal(openEnded.createdAfter, new Date(2026, 6, 1, 0, 0, 0, 0).toISOString());
assert.equal(openEnded.createdBefore, undefined, "A custom range with no end date stays open");

// The intake dropdown must only offer batches that actually reached the board.
const options = promotedCaptureSessions([
  session({ id: "empty", promoted_item_count: 0 }),
  session({ id: "older", created_at: new Date(2026, 6, 14, 9, 0).toISOString() }),
  session({ id: "newest", created_at: new Date(2026, 6, 15, 14, 32).toISOString() })
]);
assert.deepEqual(
  options.map((option) => option.id),
  ["newest", "older"],
  "Only promoted batches appear, newest first"
);

// Douyin only gives us a sec_uid, never a nickname, so the label must stay short and
// readable instead of pasting a 70-character identifier into the dropdown.
const secUid = "MS4wLjABAAAAneMf8y1oODoWZQSIuTD2T87aH-Pjin3iOtu_PbB2eqNDuPFg-Mrm_9S85DPu7c_5";
const label = captureSessionOptionLabel(
  session({ promoted_item_count: 87, normalized_profile_identifier: secUid }),
  NOW
);
assert.match(label, /87 clips/, "The option must show how many clips the batch pushed");
assert.ok(label.length <= 40, `The option label must stay readable, got ${label.length} chars: ${label}`);
assert.doesNotMatch(label, /MS4wLjABAAAAneMf/, "The raw sec_uid must never be pasted into the label");
assert.match(label, /Pu7c_5/, "A short tail of the profile id keeps two same-day batches distinguishable");

const noProfile = captureSessionOptionLabel(
  session({ promoted_item_count: 3, normalized_profile_identifier: null, submitted_profile_url: null }),
  NOW
);
assert.match(noProfile, /3 clips/, "A batch with no profile evidence still reports its size");
assert.doesNotMatch(noProfile, /·\s*$/, "The label must not end with a dangling separator");

// The Apply/Reset affordances need to know whether an intake filter is narrowing the board.
assert.equal(intakeFiltersActive({ captureSessionId: "", dateChip: "", dateFrom: "", dateTo: "" }), false);
assert.equal(intakeFiltersActive({ captureSessionId: "session-1", dateChip: "", dateFrom: "", dateTo: "" }), true);
assert.equal(intakeFiltersActive({ captureSessionId: "", dateChip: "today", dateFrom: "", dateTo: "" }), true);

// The filter has to run on the server: the board pages 200 rows at a time and reads its
// tile counts from the API, so a client-side filter would report totals that do not match.
assert.match(
  apiSource,
  /export async function fetchCandidates[\s\S]{0,900}params\.set\("capture_session_id", filters\.captureSessionId\)/,
  "fetchCandidates must send the intake batch filter to the API"
);
assert.match(
  apiSource,
  /export async function fetchCandidates[\s\S]{0,1200}params\.set\("created_after"/,
  "fetchCandidates must send the date lower bound to the API"
);
assert.match(
  apiSource,
  /export async function fetchCandidates[\s\S]{0,1200}params\.set\("created_before"/,
  "fetchCandidates must send the date upper bound to the API"
);

// Deep link: promoting from Capture Inbox lands on a board already scoped to that batch.
assert.match(
  reviewPageSource,
  /searchParams\.get\("capture_session"\)/,
  "Review Board must accept a capture_session deep link"
);
assert.match(
  reviewPageSource,
  /<IntakeFilterRow/,
  "Review Board must render the shared intake filter row"
);

// Picking a batch or a day is a discrete choice like the status tabs, so it must take
// effect on the spot. Making the operator hunt for "Apply filters" reads as a dead control.
assert.match(
  reviewPageSource,
  /function applyIntakeChange[\s\S]{0,400}setAppliedFilters/,
  "Choosing an intake filter must update the server-applied filters immediately"
);
assert.match(
  reviewPageSource,
  /onIntakeChange=\{applyIntakeChange\}/,
  "The intake row must be wired to the immediate intake handler"
);
assert.match(
  rowSource,
  /onChange\(\{ captureSessionId: event\.target\.value \}\)/,
  "The batch dropdown must apply on selection"
);
assert.match(
  rowSource,
  /onClick=\{\(\) => onChange\(\{ dateChip:/,
  "The date chips must apply on click"
);
assert.doesNotMatch(
  rowSource,
  /Apply filters to refresh counts and the gallery/,
  "The stale 'press Apply' hint must go once intake filters apply themselves"
);

// The intake row must speak the same icon language as the rest of the studio chrome.
assert.match(
  rowSource,
  /INTAKE_DATE_CHIPS: Array<\{ key: IntakeDateChip; label: string; icon: CaptureInboxFilterChipIconKind \}>/,
  "Each date chip must declare an icon"
);
assert.match(
  rowSource,
  /review-board-intake-filter__chips[\s\S]{0,900}<CaptureInboxFilterChipIcon/,
  "Date chips must render their icon"
);
assert.match(
  rowSource,
  /review-board-filter-control__label[\s\S]{0,200}kind="lane-captured"/,
  "The batch picker must carry the Capture Inbox lane icon"
);

// Layout + feedback: the strip must span the filter deck, and picking a filter must
// freeze the controls and tell the gallery it is busy — otherwise a slow response
// looks like a dead control.
const stylesSource = readFileSync(resolve(webSrcDir, "app/globals.css"), "utf8");
const intakeCss = stylesSource.slice(
  stylesSource.indexOf(".review-board-intake-filter {"),
  stylesSource.indexOf(".review-board-score-range__title")
);
assert.match(intakeCss, /width:\s*100%/, "The intake strip must span the full filter deck width");
assert.doesNotMatch(
  intakeCss,
  /max-width:\s*34rem/,
  "The batch dropdown must not be capped short of the row"
);
// The short white card was `.is-intake` sharing flex-grow with the chips. The row itself
// must be the full-bleed surface, batch grows, and chips stay content-sized on the right.
assert.match(
  intakeCss,
  /\.review-board-intake-filter \.review-board-filter-control\.is-intake\s*\{[^}]*flex:\s*1 1 auto/,
  "The batch control must grow across the free width of the strip"
);
assert.match(
  intakeCss,
  /\.review-board-intake-filter__chips\s*\{[^}]*flex:\s*0 0 auto/,
  "Date chips must not steal half the strip and leave a short white batch card"
);
assert.match(
  intakeCss,
  /\.review-board-intake-filter \.review-board-filter-control\.is-intake\s*\{[^}]*(?:border:\s*none|background:\s*transparent)/,
  "Nested batch chrome must not invent a second, shorter white card inside the strip"
);
assert.match(
  rowSource,
  /busy\??: boolean/,
  "IntakeFilterRow must accept a busy flag while the gallery reloads"
);
assert.match(
  rowSource,
  /disabled=\{busy\}/,
  "Intake controls must freeze while the filtered request is in flight"
);
assert.match(
  rowSource,
  /is-busy|aria-busy=\{busy\}/,
  "The row must expose a busy state for the loading affordance"
);
assert.match(
  reviewPageSource,
  /busy=\{intakeBusy\}|busy=\{galleryBusy\}|busy=\{filterBusy\}/,
  "Review Board must pass its intake/gallery busy flag into the shared row"
);
assert.match(
  reviewPageSource,
  /intakeBusy|galleryBusy|filterBusy/,
  "Review Board must treat an in-flight intake reload as a visible gallery busy state"
);

console.log("review-board-intake-filter tests passed");
