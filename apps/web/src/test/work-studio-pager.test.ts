/**
 * Work pagination — Concept C studio pager (+ auto-load on gallery surfaces).
 * Validates plan PASS checklist from work_studio_pager plan.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const footerSource = readFileSync(resolve(webSrc, "components/shared/OffsetLoadMoreFooter.tsx"), "utf8");
const hookSource = readFileSync(resolve(webSrc, "components/shared/useOffsetLoadMoreOnScroll.ts"), "utf8");
const paginationSource = readFileSync(resolve(webSrc, "lib/offsetListPagination.ts"), "utf8");
const captureSource = readFileSync(resolve(webSrc, "components/capture-inbox/CaptureInboxPage.tsx"), "utf8");
const reviewSource = readFileSync(resolve(webSrc, "components/review-board/ReviewBoardPage.tsx"), "utf8");
const reupSource = readFileSync(resolve(webSrc, "components/reup-queue/ReupQueuePage.tsx"), "utf8");
const cssSource = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

// Concept C — centered soft CTA shell
assert.match(footerSource, /variant\?: "default" \| "inline" \| "studio"/, "Footer must support studio variant");
assert.match(footerSource, /formatOffsetShowingLabel/, "Studio pager must use Showing X of Y meta");
assert.match(footerSource, /work-studio-pager__cta/, "Manual studio branch must render soft Load next CTA");
assert.match(footerSource, /work-studio-pager__complete/, "Studio pager must show All loaded complete state");
assert.match(paginationSource, /formatOffsetLoadNextLabel/, "Concept C must use Load next N label helper");
assert.match(cssSource, /\.work-studio-pager__meta/, "CSS must style centered studio pager meta");
assert.match(cssSource, /\.work-studio-pager__cta/, "CSS must style soft CTA button");

assert.match(footerSource, /autoLoad\?: boolean/, "Footer must accept autoLoad prop");
assert.match(footerSource, /is-auto-load/, "Studio pager must render auto-load layout");
assert.match(footerSource, /Scroll for more/, "Auto-load pager must show scroll hint");
assert.match(footerSource, /if \(autoLoad\)/, "Studio variant must branch for auto-load UI");
assert.match(footerSource, /work-studio-pager__track/, "Auto-load pager must include progress track");
assert.doesNotMatch(
  footerSource.slice(footerSource.indexOf("if (autoLoad)"), footerSource.indexOf("return (", footerSource.indexOf("if (autoLoad)") + 1)),
  /work-studio-pager__cta/,
  "Auto-load branch must not render Load next CTA"
);

assert.match(hookSource, /export function useOffsetLoadMoreOnScroll/, "Shared scroll auto-load hook must exist");
assert.match(hookSource, /IntersectionObserver/, "Hook must observe sentinel intersection");
assert.match(hookSource, /pendingRef/, "Hook must guard in-flight loads to prevent scroll flicker");
assert.match(hookSource, /loadedCount/, "Hook must track loaded count to detect stalled tail pages");

assert.match(footerSource, /holdLoadingHint/, "Auto-load pager must hold loading hint briefly to avoid flicker");

assert.match(cssSource, /\.work-studio-pager\.is-auto-load/, "CSS must style auto-load pager");
assert.match(cssSource, /\.work-studio-pager__track/, "CSS must style progress track");

// Wire — Capture gallery auto-load; session rail manual CTA
const sessionRibbonSource = captureSource.slice(
  captureSource.indexOf("function SessionRibbon"),
  captureSource.indexOf("function MediaTileGallery")
);
assert.doesNotMatch(sessionRibbonSource, /autoLoad/, "Capture session rail must use manual studio CTA without auto-load");
assert.match(sessionRibbonSource, /variant="studio"/, "Capture session rail must use studio pager");

assert.match(captureSource, /autoLoad/, "Capture gallery pager must auto-load on scroll");
assert.match(captureSource, /useOffsetLoadMoreOnScroll/, "Capture gallery must use shared scroll auto-load hook");
assert.doesNotMatch(
  captureSource.slice(captureSource.indexOf("function MediaTileGallery")),
  /new IntersectionObserver/,
  "Capture gallery must not duplicate IntersectionObserver beside shared hook"
);
assert.match(captureSource, /variant="studio"/, "Capture must use studio pager on gallery and sessions");

// Wire — Review + Reup unified studio auto-load pager
assert.match(reviewSource, /useOffsetLoadMoreOnScroll/, "Review Board must wire scroll auto-load");
assert.match(reviewSource, /autoLoad/, "Review Board pager must use auto-load UI");
assert.match(reviewSource, /variant="studio"/, "Review Board must use studio pager");
assert.match(reupSource, /useOffsetLoadMoreOnScroll/, "Reup Queue must wire scroll auto-load");
assert.match(reupSource, /autoLoad/, "Reup Queue pager must use auto-load UI");
assert.match(reupSource, /variant="studio"/, "Reup Queue must use studio pager");
assert.doesNotMatch(reupSource, /Load next.*queue items/, "Reup must not expose legacy Load next queue items copy");

// PASS — no plain scroll-hint sentinel copy on Capture gallery
assert.doesNotMatch(captureSource, /Scroll to load more items/, "Capture gallery must not keep legacy scroll-hint copy");

console.log("work-studio-pager tests passed");