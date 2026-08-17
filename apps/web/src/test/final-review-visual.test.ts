import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
const headerSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewHeader.tsx"), "utf8");
const actionsSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewActions.tsx"), "utf8");
const statesSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewStates.tsx"), "utf8");
const visualSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"), "utf8");
const readinessSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewReadinessStrip.tsx"),
  "utf8"
);
const previewSource = readFileSync(resolve(testDir, "../components/final-review/FinalCompareViewer.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
  finalReviewTabs: Record<string, string>;
  finalReviewActions: Record<string, string>;
  finalReviewHeader: Record<string, string>;
  transcriptEditorHeader: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
  finalReviewTabs: Record<string, string>;
  finalReviewActions: Record<string, string>;
  finalReviewHeader: Record<string, string>;
};

assert.match(apiSource, /export async function createOcrJob/, "API must expose createOcrJob");
assert.match(apiSource, /export async function fetchOcrSummary/, "API must expose fetchOcrSummary");
assert.match(apiSource, /export async function approveOcrVisual/, "API must expose approveOcrVisual");
assert.match(pageSource, /FinalReviewVisualCheckpoint/, "Final Review must mount visual checkpoint");
assert.match(pageSource, /maxAttempts:\s*1800/, "OCR poll must allow a long CPU Paddle budget");
assert.match(apiSource, /sample_fps:\s*1\.0/, "OCR create should default to 1 fps for hard-sub pilot");
assert.match(pageSource, /handleApproveVisual/, "Final Review must run visual approve");
assert.match(
  visualSource,
  /analyzeBusy|approveBusy/,
  "Visual CTAs must use separate analyze/approve busy flags so Approve is not stuck on Analyzing"
);
assert.match(
  visualSource,
  /!summary\.cleaned_video_asset_id/,
  "Quality visual approval must stay locked until a cleaned preview exists"
);
assert.match(
  visualSource,
  /canRegenerateQualityPreview[\s\S]*retryPreview/,
  "Quality previews must be regeneratable without rerunning OCR"
);
assert.match(
  visualSource,
  /defaultOcrReviewChoice[\s\S]{0,300}ocr_text_candidate\?\.trim\(\)[\s\S]{0,120}:\s*""/,
  "An empty OCR candidate must require an explicit decision instead of invalid APPROVE"
);
assert.match(visualSource, /option value="REJECT_UI"/, "OCR review must expose false-detection rejection");
assert.match(visualSource, /!value\.decision/, "OCR review submit must stay disabled while a decision is unresolved");
assert.match(apiSource, /"REJECT_UI"/, "OCR review API type must accept REJECT_UI");
assert.ok(en.finalReviewVisual.reviewRejectUi.length > 0);
assert.ok(vi.finalReviewVisual.reviewRejectUi.length > 0);
{
  assert.match(
    pageSource,
    /presentation=\{prepFocus === "ocr" \? "prep" : "prep-bar"\}|presentation="prep"/,
    "Prep layout must mount Visual checkpoint with presentation=prep when OCR-focused"
  );
  assert.match(
    pageSource,
    /analyzeBusy:\s*ocrBusy|analyzeBusy=\{ocrBusy\}/,
    "Prep Visual checkpoint must busy only on OCR, not on Start-render actionBusy"
  );
  assert.doesNotMatch(
    pageSource,
    /analyzeBusy:\s*ocrBusy\s*\|\|\s*actionBusy|analyzeBusy=\{ocrBusy \|\| actionBusy\}/,
    "Prep must not show Analyzing OCR while Start first render is pending"
  );
}
assert.match(
  pageSource,
  /final-review-prep-stage|final-review-prep-col/,
  "Prep layout must use the original dual-panel stage (Visual + Up next)"
);
assert.match(
  pageSource,
  /is-hero|is-side/,
  "Prep dual panels must mark hero vs side by prepFocus"
);
assert.match(
  pageSource,
  /FinalReviewPrepJourney|final-review-prep-journey/,
  "Prep must keep the short-label journey rail"
);
assert.doesNotMatch(
  pageSource,
  /presentation="prep-bar"/,
  "Prep must not collapse Visual into prep-bar"
);
assert.ok(en.finalReviewVisual.approving.length > 0);
assert.ok(vi.finalReviewVisual.approving.length > 0);
assert.match(pageSource, /handleStartFirstRender/, "Empty Final Review must start first render");
assert.match(
  pageSource,
  /announceRenderLifecycle|renderQueued[\s\S]{0,220}tone:\s*"info"/,
  "Start/rerender must toast when the render job is queued (pre-render)"
);
assert.match(
  pageSource,
  /notify\(\{[\s\S]*renderInProgress[\s\S]*tone:\s*"info"[\s\S]*durationMs:\s*null/,
  "Start/rerender must toast sticky progress while the render job runs"
);
assert.match(
  pageSource,
  /notify\(\{[\s\S]*renderSuccess[\s\S]*tone:\s*"success"/,
  "Start/rerender must toast when the first render completes"
);
assert.match(
  pageSource,
  /const queued = t\("finalReviewStates\.renderQueued"\)[\s\S]*notify\(\{ id: `\$\{noticeId\}-queued`/,
  "Queued toast must use the renderQueued copy with a distinct notice id"
);
assert.doesNotMatch(
  pageSource,
  /setOcrMessage\(t\("finalReviewStates\.renderQueued"\)|setActionMessage\(queued\)/,
  "Render queued copy must not appear as inline OCR/action message — toast only"
);
assert.match(
  pageSource,
  /renderFailed[\s\S]*tone:\s*"error"/,
  "Start/rerender must toast when the render job fails"
);
{
  const startRenderFn = pageSource.match(
    /async function handleStartFirstRender\(\)[\s\S]*?(?=async function handleRerender\(\))/
  )?.[0] ?? "";
  const rerenderFn = pageSource.match(
    /async function handleRerender\(\)[\s\S]*?(?=function pauseRenderWatch\(|async function pauseRenderWatch\(|function clearOcrWatchSession\()/
  )?.[0] ?? "";
  assert.ok(startRenderFn.length > 0 && rerenderFn.length > 0, "Must locate start/rerender handlers");
  assert.doesNotMatch(startRenderFn, /setError\((?!null\))/, "Start first render failures must toast only, not inline error");
  assert.doesNotMatch(rerenderFn, /setError\((?!null\))/, "Rerender failures must toast only, not inline error");
}
assert.match(
  pageSource,
  /resumeActiveOcrJob|pickActiveOcrJob/,
  "Final Review must re-attach in-flight ANALYZE_OCR after reload"
);
assert.ok(en.finalReviewStates.renderInProgress.length > 0);
assert.ok(vi.finalReviewStates.renderInProgress.length > 0);
assert.match(
  pageSource,
  /settleRenderOutcome[\s\S]{0,400}loadData\(\)|async function handleRerender\(\)[\s\S]*?pollRenderJob[\s\S]*?settleRenderOutcome/,
  "Rerender must poll job and reload latest render so Warnings panel is not stale"
);
assert.match(pageSource, /fr-rail/, "Final Review must use tabbed rail");
assert.match(pageSource, /railTab/, "Final Review must keep rail tab state");
assert.match(pageSource, /fr-workspace/, "Final Review must use cinema workspace layout");
assert.match(
  cssSource,
  /\.fr-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(380px,\s*440px\)/,
  "Final Review rail must be wider (~400–440px) so checklist/warnings are readable"
);
assert.match(actionsSource, /fr-decision-bar/, "Decision actions must render sticky decision bar");
assert.doesNotMatch(
  actionsSource,
  /fr-decision-bar__hint/,
  "Compact decision bar must not always show the long approve/publish hint paragraph"
);
assert.match(
  actionsSource,
  /title=\{[^}]*approveExportHint|title=\{t\(["']finalReviewActions\.approveExportHint["']\)\}/,
  "Approve/publish guidance must stay available via button title tooltips"
);
assert.doesNotMatch(
  actionsSource,
  /warning-line/,
  "Decision bar warnings must not use the tall warning-line box"
);
assert.match(
  actionsSource,
  /fr-decision-bar__warn|fr-decision-bar__meta/,
  "Warnings must surface as a compact meta chip beside checklist progress"
);
assert.match(
  actionsSource,
  /leadingIcon[\s\S]*kind=["']approve["'][\s\S]*approveExport|kind=["']approve["'][\s\S]*leadingIcon[\s\S]*approveExport/,
  "Approve export must show approve icon + text"
);
assert.match(
  actionsSource,
  /leadingIcon[\s\S]*kind=["']promote["'][\s\S]*markPublishReady|kind=["']promote["'][\s\S]*leadingIcon[\s\S]*markPublishReady/,
  "Mark publish-ready must show promote icon + text"
);
assert.match(
  pageSource,
  /railTab\s*===\s*["']review["'][\s\S]*?FinalReviewActions|FinalReviewActions[\s\S]*?railTab\s*===\s*["']review["']/,
  "Decision bar must mount only on Review tab (Phase 1 focus)"
);
assert.doesNotMatch(
  headerSource,
  /onApprove|onPublishReady|approveExport|markPublishReady/,
  "Header must not duplicate Approve / Publish-ready CTAs"
);
assert.match(headerSource, /fr-topbar--compact|fr-topbar__status/, "Header must use compact Phase 1 status strip");
assert.match(headerSource, /fr-topbar__actions/, "Header tools must stay visible in a compact action row");
assert.doesNotMatch(headerSource, /fr-topbar__more|<details/, "Header must not hide tools in a More menu");
assert.match(headerSource, /onRerender|rerender/, "Rerender must stay a visible header action");
assert.doesNotMatch(
  headerSource,
  /transcript-editor|\/publish|review-board/,
  "Cross-page nav (Transcript / Publish / Board) must live in Operator shell topbar, not Final Review header"
);
assert.doesNotMatch(
  pageSource,
  /final-review-preheader__actions/,
  "Prep preheader must not duplicate shell topbar Transcript link"
);
assert.doesNotMatch(
  pageSource,
  /final-review-preheader[\s\S]{0,200}<h1>|fr-topbar__kicker[\s\S]{0,80}finalReviewHeader\.title/,
  "Prep must not render a second Final Review title — Operator shell already owns the page chrome"
);
assert.doesNotMatch(
  headerSource,
  /fr-topbar__gates[\s\S]*fr-gate[\s\S]*fr-gate/,
  "Header must not show two always-visible readiness gates"
);
assert.match(headerSource, /fr-topbar--dossier|fr-topbar__meta/, "Header must use dossier meta layout");
assert.match(
  headerSource,
  /fr-topbar__toolbar[\s\S]*fr-topbar__lead[\s\S]*fr-topbar__kicker[\s\S]*fr-topbar__meta|fr-topbar__lead[\s\S]*fr-topbar__kicker[\s\S]*fr-topbar__meta/,
  "Compact dossier must place status meta on the toolbar lead beside FINAL REVIEW"
);
assert.match(
  headerSource,
  /fr-topbar__main[\s\S]*fr-topbar__title/,
  "Title row must remain under the toolbar"
);
assert.doesNotMatch(
  headerSource,
  /fr-topbar__identity[\s\S]*fr-topbar__meta|fr-topbar__title[\s\S]{0,80}fr-topbar__meta/,
  "Meta must not duplicate under the title once moved to the toolbar lead"
);
assert.match(
  cssSource,
  /\.fr-review-chrome\s*\{[^}]*gap:\s*(8|9|10)px/s,
  "Review chrome must stay compact (gap ≤ 10px)"
);
assert.match(
  cssSource,
  /\.final-review-readiness__metric\s*\{[^}]*padding:\s*[4-8]px/s,
  "Readiness metric cells must use compact padding"
);
assert.match(
  cssSource,
  /\.final-review-readiness__status[\s\S]{0,220}overflow:\s*hidden|\.final-review-readiness__status[\s\S]{0,220}text-overflow:\s*ellipsis/,
  "Still-needed status must truncate on one line"
);
assert.doesNotMatch(
  headerSource,
  /needsExportApproval|exportApproved|mediaPublishReady/,
  "Header must not duplicate approval/publish chips — readiness strip owns those gates"
);
assert.doesNotMatch(
  headerSource,
  /getRenderWarnings|warnings\.length/,
  "Header must not duplicate warning count chips — readiness strip owns WARNINGS"
);
assert.doesNotMatch(
  headerSource,
  /fr-chip/,
  "Dossier header uses quiet meta text, not chip badges"
);
assert.match(
  headerSource,
  /humanizeStatus\(render\.status\)/,
  "Header status must use humanizeStatus(render.status)"
);
assert.match(
  cssSource,
  /\.fr-topbar--compact\s+\.fr-topbar__main[\s\S]{0,80}align-items:\s*flex-start/,
  "Compact header identity column must stay top-aligned"
);
assert.match(
  cssSource,
  /\.fr-topbar__toolbar[\s\S]{0,120}justify-content:\s*space-between|\.fr-topbar__toolbar[\s\S]{0,80}display:\s*flex/,
  "Rerender must sit on the FINAL REVIEW toolbar row (top-right)"
);
assert.match(
  headerSource,
  /fr-topbar__toolbar/,
  "Dossier header must use a toolbar row for kicker + Rerender"
);
assert.doesNotMatch(
  headerSource,
  /fr-topbar--hud|fr-topbar--merged/,
  "Header must not use broken HUD / merged band experiments"
);
assert.doesNotMatch(
  pageSource,
  /fr-review-chrome--hud/,
  "Workspace chrome must not enable HUD strip layout"
);
assert.match(
  cssSource,
  /\.final-review-readiness__head\s*\{[^}]*display:\s*flex/s,
  "Publish readiness head must be one horizontal row (title + still-needed)"
);
assert.match(
  readinessSource,
  /final-review-readiness__head/,
  "Readiness strip must keep a dedicated head row for title + status"
);
assert.match(
  readinessSource,
  /final-review-readiness--rail|final-review-readiness__metrics/,
  "Readiness must use divider metric rail, not pill chips"
);
assert.match(
  readinessSource,
  /final-review-readiness--panel/,
  "Readiness must use the stable panel scoreboard"
);
assert.doesNotMatch(
  readinessSource,
  /final-review-readiness--hud|final-review-readiness--flush|final-review-readiness__badge/,
  "Readiness must not use HUD chips / flush / badge experiments"
);
assert.match(
  pageSource,
  /fr-review-chrome/,
  "Header + readiness must share one sticky chrome surface"
);
assert.match(
  headerSource,
  /fr-tool--quiet|fr-tool--primary/,
  "Rerender must stay a visible compact header action"
);
assert.match(
  cssSource,
  /\.fr-review-chrome\s*\{[^}]*position:\s*sticky/s,
  "Review chrome must stick as one unit above the compare workspace"
);
assert.match(
  readinessSource,
  /is-ready|is-blocked/,
  "Readiness section must expose ready/blocked modifiers for panel styling"
);
assert.match(
  readinessSource,
  /publishReady[\s\S]{0,120}is-ready|blockers[\s\S]{0,160}is-blocked/,
  "Readiness modifiers must derive from publishReady / blockers authority"
);
assert.match(cssSource, /aspect-ratio:\s*16\s*\/\s*9/, "Compare panes must use landscape 16:9");
assert.doesNotMatch(
  cssSource,
  /\.final-compare[\s\S]{0,500}aspect-ratio:\s*9\s*\/\s*16|\.compare-pane[\s\S]{0,200}aspect-ratio:\s*9\s*\/\s*16/,
  "Compare panes must not force portrait 9:16"
);
assert.match(statesSource, /startRender/, "Empty state must expose start render CTA");
assert.doesNotMatch(statesSource, /onAnalyzeOcr/, "Analyze OCR belongs on the Visual Clean side card, not embedded in First Render");
assert.match(statesSource, /resolveFinalReviewPrepFocus|prepFocus|ocrPrep/, "Prep empty state must resolve OCR-first vs render focus");
assert.match(
  statesSource,
  /is-active|prepFocus\s*===\s*["']ocr["']|prepFocus\s*===\s*["']render["']/,
  "Prep step rail must mark the active OCR or render step"
);
assert.match(
  statesSource,
  /prepFocus\s*===\s*["']render["'][\s\S]*primary|renderIsPrimary[\s\S]*primary/,
  "Start first render must be primary only after OCR prep focus moves to render"
);
assert.match(
  pageSource,
  /FinalReviewEmptyState[\s\S]*prepFocus|emptyProps[\s\S]*prepFocus|prepFocus=\{resolveFinalReviewPrepFocus/,
  "Prep page must pass prepFocus from OCR summary into empty state"
);
assert.match(
  visualSource,
  /is-prep-focus|presentation === "prep"/,
  "Visual Clean prep card must emphasize Analyze OCR while OCR focus is active"
);
assert.match(
  statesSource,
  /emptyBodyReady|prepFocus\s*===\s*["']render["'][\s\S]{0,220}emptyBody/,
  "First-render hero must use ready copy once prepFocus is render"
);
assert.ok(en.finalReviewStates.emptyBodyReady, "EN must define ready-state first-render body copy");
assert.ok(vi.finalReviewStates.emptyBodyReady, "VI must define ready-state first-render body copy");
assert.match(
  visualSource,
  /approveNeedsFocus[\s\S]{0,200}is-prep-focus|prepFocus\s*===\s*["']render["'][\s\S]{0,500}is-prep-focus/,
  "When Clean is done, Approve (if pending) must take prep focus instead of Analyze"
);
assert.match(
  visualSource,
  /final-visual-checkpoint__split/,
  "Prep Visual Clean must use a media/copy split layout"
);
assert.match(
  visualSource,
  /final-visual-checkpoint__preview-stage[\s\S]{0,800}final-visual-checkpoint__copy/,
  "Prep Visual Clean must place preview before the copy column (video left, text right)"
);
assert.match(
  cssSource,
  /\.final-review--prep[\s\S]{0,80}\.final-visual-checkpoint__split[\s\S]{0,160}grid-template-columns:\s*auto/,
  "Prep Visual media column must size to the video instead of a fixed width track"
);
assert.match(
  visualSource,
  /videoWidth|onLoadedMetadata|previewAspect/,
  "Prep preview must read intrinsic video dimensions for adaptive framing"
);
assert.doesNotMatch(
  cssSource,
  /\.final-review--prep[\s\S]{0,400}\.final-visual-checkpoint__preview[\s\S]{0,120}aspect-ratio:\s*9\s*\/\s*16/,
  "Prep cleaned preview must not hardcode 9:16 — size must follow the clip"
);
assert.match(
  cssSource,
  /\.final-visual-checkpoint__preview[\s\S]{0,120}max-height:|\.preview-stage[\s\S]{0,200}max-width:/,
  "Adaptive preview must still clamp max size so tall/wide clips stay usable"
);
assert.match(
  cssSource,
  /\.final-visual-checkpoint__approve\.(primary|is-prep-focus)|approve\.primary[\s\S]{0,80}background:\s*var\(--accent\)/,
  "Approve primary must not be flattened by the quiet approve override"
);
assert.match(
  visualSource,
  /is-prep-quiet/,
  "Analyze OCR must demote to quiet once prep focus leaves OCR"
);
assert.ok(en.finalReviewVisual.analyzeOcrShort, "EN must define short Analyze OCR label for prep");
assert.ok(en.finalReviewVisual.reanalyzeOcrShort, "EN must define short Re-Analyze OCR label after first run");
assert.ok(en.finalReviewVisual.approveVisualShort, "EN must define short Approve label for prep");
assert.ok(en.finalReviewVisual.cleanedReadyShort, "EN must define short cleaned-ready status for prep");
assert.ok(vi.finalReviewVisual.analyzeOcrShort, "VI must define short Analyze OCR label for prep");
assert.ok(vi.finalReviewVisual.reanalyzeOcrShort, "VI must define short Re-Analyze OCR label after first run");
assert.ok(vi.finalReviewVisual.approveVisualShort, "VI must define short Approve label for prep");
assert.ok(vi.finalReviewVisual.cleanedReadyShort, "VI must define short cleaned-ready status for prep");
assert.match(
  visualSource,
  /hasFinalReviewOcrRun/,
  "Visual Clean Analyze CTA must use hasFinalReviewOcrRun (not bare Boolean summary)"
);
assert.match(
  visualSource,
  /reanalyzeOcrShort|reanalyzeOcr/,
  "Visual Clean Analyze CTA must switch to Re-Analyze after a prior OCR run"
);
assert.match(
  statesSource,
  /hasFinalReviewOcrRun/,
  "Prep journey Clean CTA must use hasFinalReviewOcrRun for Re-clean vs Start clean"
);
assert.match(
  visualSource,
  /useShortPrepLabels[\s\S]{0,200}analyzeOcrShort|finalReviewVisual\.analyzeOcrShort/,
  "Prep Visual CTAs must use short labels"
);
assert.match(
  visualSource,
  /final-visual-checkpoint--rail/,
  "Rail Visual checkpoint must use compact rail presentation"
);
assert.match(
  visualSource,
  /presentation === "rail"/,
  "Rail Visual must detect rail presentation for short labels"
);
assert.match(
  visualSource,
  /titleShort/,
  "Rail Visual must prefer the short Hard-sub visual title"
);
assert.match(
  visualSource,
  /final-visual-checkpoint--rail[\s\S]{0,400}__preview[\s\S]{0,500}__rail-toolbar|final-visual-checkpoint__preview[\s\S]{0,200}final-visual-checkpoint__rail-toolbar/,
  "Rail Visual must use preview-first layout (preview above action toolbar)"
);
assert.match(
  visualSource,
  /final-visual-checkpoint__header|__lead-row/,
  "Prep Visual copy must keep eyebrow + status on a compact header row"
);
assert.match(
  cssSource,
  /\.final-review--prep[\s\S]{0,200}\.final-visual-checkpoint__steps[\s\S]{0,220}border-radius:\s*999px/,
  "Prep Visual CTAs must use compact pill buttons"
);
assert.match(
  en.finalReviewStates.emptyPrepHint,
  /Visual Clean|OCR|first render/i,
  "Prep hint must guide operators through Clean then first render"
);
assert.doesNotMatch(
  en.finalReviewStates.emptyPrepHint,
  /\bon the right\b/i,
  "Prep hint must not hardcode card side (hero/side swap by focus)"
);
assert.ok(en.finalReviewStates.emptyStepShort1, "EN must define short journey label for Clean");
assert.ok(en.finalReviewStates.emptyStepShort2, "EN must define short journey label for Render");
assert.ok(en.finalReviewStates.emptyStepShort3, "EN must define short journey label for Compare");
assert.ok(en.finalReviewStates.emptyUpNext, "EN must define Up next panel eyebrow");
assert.doesNotMatch(
  en.finalReviewStates.emptyStepShort1,
  /Analyze OCR|hard-sub/i,
  "Short step 1 must not duplicate the Analyze OCR CTA wording"
);
assert.match(
  en.transcriptEditorHeader.finalReviewShort,
  /Open Final Review/,
  "Transcript Final CTA must read as Open Final Review, not bare Final"
);
assert.match(
  statesSource,
  /FinalReviewPrepJourney|emptyStepShort1/,
  "Prep journey must use short step labels (Clean / Render / Compare)"
);
assert.match(statesSource, /final-review-prep-journey|final-review-empty__step-rail/, "Prep must show a numbered step rail");
assert.match(statesSource, /final-review-empty__secondary|emptyUpNext/, "Empty/Up-next panel must expose secondary links");
assert.match(
  statesSource,
  /presentation\?: "hero" \| "side" \| "bar"|presentation === "bar"|empty--bar/,
  "Empty state must support hero, side, and render-focus action bar"
);
assert.match(cssSource, /\.final-review-prep-stage/, "CSS must style the dual-panel prep stage");
assert.match(
  cssSource,
  /\.final-review-prep-stage\s*\{[^}]*align-items:\s*stretch/,
  "Prep stage must stretch dual panels to a shared row height"
);
assert.match(
  cssSource,
  /\.final-review-empty--side[\s\S]{0,220}height:\s*100%|\.final-review-prep-col\.is-side[\s\S]{0,200}height:\s*100%/,
  "Side Up-next card must fill the stretched column height"
);
assert.match(
  cssSource,
  /\.final-review-empty__actions--side[\s\S]{0,220}margin-top:\s*auto/,
  "Side Up-next actions must pin to the card bottom when heights sync"
);
assert.ok(en.finalReviewStates.emptySideCue, "EN must define a quiet side outcome cue for operators");
assert.ok(vi.finalReviewStates.emptySideCue, "VI must define a quiet side outcome cue for operators");
assert.match(
  statesSource,
  /emptySideCue|final-review-empty__side-cue/,
  "Side Up-next must show a quiet outcome cue so the tall card is not empty"
);
assert.match(
  cssSource,
  /\.final-review-prep-stage\.is-focus-render[\s\S]{0,160}grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  "Render-focus stage must stack as a single full-width column (action strip + Visual Clean)"
);
assert.match(
  cssSource,
  /\.final-review-empty--bar/,
  "Render-focus First Render must use a compact horizontal action bar, not a stub card"
);
assert.match(
  statesSource,
  /final-review-empty__bar-top|empty__bar-nav/,
  "First-render bar must place Transcript/Board in the top-right header row"
);
assert.match(
  statesSource,
  /final-review-empty__bar-status/,
  "Running status strip must sit in its own full-width bar row"
);
assert.match(
  cssSource,
  /\.final-review-empty__bar-status[\s\S]{0,80}width:\s*100%|\.final-review-empty__bar-status[\s\S]{0,120}\.fr-action-status[\s\S]{0,40}width:\s*100%/,
  "Bar status strip must span the full horizontal width"
);
assert.match(
  cssSource,
  /\.final-review-empty__bar-top[\s\S]{0,120}justify-content:\s*space-between/,
  "Bar header must keep title left and Transcript/Board right"
);
assert.match(
  statesSource,
  /final-review-empty__bar-top[\s\S]{0,500}startRenderButton[\s\S]{0,200}barNav|final-review-empty__bar-actions[\s\S]{0,300}startRenderButton/,
  "Start render must sit on the bar top row with Transcript/Board (including after render failed)"
);
assert.doesNotMatch(
  statesSource,
  /bar-status[\s\S]{0,400}actions--bar-cta/,
  "Start render must not sit below the full-width status strip as a separate CTA row"
);
assert.match(
  statesSource,
  /final-review-empty__primary--compact|secondary--inline/,
  "Bar CTAs must use compact primary + inline secondary links"
);
assert.ok(en.finalReviewStates.emptySideTitle, "EN must define short Up-next side title");
assert.ok(vi.finalReviewStates.emptySideTitle, "VI must define short Up-next side title");
assert.ok(en.finalReviewStates.emptyBodySideShort, "EN must define compact Up-next side body");
assert.ok(vi.finalReviewStates.emptyBodySideShort, "VI must define compact Up-next side body");
assert.match(
  statesSource,
  /useCompactActions[\s\S]{0,220}startRenderShort|finalReviewStates\.startRenderShort/,
  "Side Up-next must use the short Start render label"
);
assert.match(
  statesSource,
  /const renderLocked\s*=\s*prepFocus\s*===\s*["']ocr["']/,
  "Up-next Start render must lock while prepFocus is still OCR/Clean"
);
assert.match(
  statesSource,
  /onStartRender\s*&&\s*!renderLocked|!renderLocked\s*&&\s*onStartRender/,
  "When the Up-next card is locked, Start render must not also render as a disabled button"
);
assert.doesNotMatch(
  statesSource,
  /primary--locked/,
  "Locked Up-next must not double-style Start render as a separate disabled button"
);
assert.ok(en.finalReviewStates.emptyBodySideLocked, "EN must define locked Up-next body while Clean is pending");
assert.ok(vi.finalReviewStates.emptyBodySideLocked, "VI must define locked Up-next body while Clean is pending");
assert.match(
  en.finalReviewStates.emptyBodySideLocked,
  /^[^\n]+$/,
  "Locked Up-next body must stay a single line"
);
assert.doesNotMatch(
  en.finalReviewStates.emptyBodySideLocked,
  /unlocks after/i,
  "Locked Up-next body must stay short enough for one line (no long unlock clause)"
);
assert.match(
  statesSource,
  /final-review-empty__lock-note|emptyBodySideLocked/,
  "Locked Up-next must show an explicit one-line lock note"
);
assert.match(
  cssSource,
  /\.final-review-empty__lock-note[\s\S]{0,160}white-space:\s*nowrap|\.final-review-empty__lock-note[\s\S]{0,120}nowrap/,
  "Lock note must force a single visual line"
);
assert.match(
  statesSource,
  /final-review-empty--locked|empty--side[\s\S]{0,80}is-locked/,
  "Locked Up-next must box the whole card cluster, not only the Start render button"
);
assert.match(
  cssSource,
  /\.final-review-empty--locked|\.final-review-empty--side\.is-locked/,
  "Locked Up-next cluster must have a full-card blocked treatment"
);
assert.match(
  statesSource,
  /transcriptEditorFull|secondary--side[\s\S]{0,200}fr-tool/,
  "Side Up-next secondary nav must use full-label icon buttons"
);
assert.match(
  statesSource,
  /isBar[\s\S]{0,320}nav-pill|final-review-empty__nav-pill/,
  "Bar First-render nav must use polished Transcript/Board pill buttons"
);
assert.match(
  cssSource,
  /final-review-empty__nav-pill[\s\S]{0,280}border-radius:\s*999px/,
  "Bar Transcript/Board pills must use round pill chrome"
);
assert.match(
  statesSource,
  /transcriptEditorFull[\s\S]{0,200}backToReviewBoard|backToReviewBoard/,
  "Side Up-next Board control must use the full Back to review board label"
);
assert.ok(en.finalReviewHeader.transcriptEditorFull, "EN must define full Transcript editor label");
assert.ok(vi.finalReviewHeader.transcriptEditorFull, "VI must define full Transcript editor label");
assert.match(
  cssSource,
  /\.final-review-empty__secondary--side[\s\S]{0,200}\.fr-tool|\.final-review-empty__actions--side[\s\S]{0,160}\.fr-tool/,
  "Side Up-next secondary buttons must get polished pill/tool styling"
);
assert.match(
  cssSource,
  /\.final-review-empty--side[\s\S]{0,280}gap:|\.final-review-empty--side[\s\S]{0,200}actions--side/,
  "Side Up-next panel must use a compact vertical rhythm"
);
assert.match(
  statesSource,
  /startRenderShort|boardShort/,
  "Bar CTAs must use short labels so the cluster stays compact"
);
assert.match(
  cssSource,
  /\.final-review-empty__primary--compact[\s\S]{0,80}border-radius:\s*999px|\.actions--bar[\s\S]{0,120}border-radius:\s*999px/,
  "Compact Start render must use a pill shape"
);
assert.ok(en.finalReviewStates.startRenderShort, "EN must define short Start render label");
assert.ok(en.finalReviewStates.boardShort, "EN must define short Board label");
assert.ok(vi.finalReviewStates.startRenderShort, "VI must define short Start render label");
assert.ok(vi.finalReviewStates.boardShort, "VI must define short Board label");
assert.match(
  pageSource,
  /presentation=\{prepFocus === "render" \? "bar"|presentation="bar"|empty--bar/,
  "When prepFocus is render, First Render must mount as the action bar"
);
assert.match(
  pageSource,
  /is-focus-\$\{prepFocus\}|is-focus-render/,
  "Prep stage must mark focus so layout can switch OCR dual-panel vs render stack"
);
assert.match(
  pageSource,
  /final-review-prep-col--span[\s\S]{0,80}\{emptyCard\}[\s\S]{0,120}final-review-prep-col--span[\s\S]{0,80}\{visualCard\}/,
  "Render-focus stage must place the action strip above full-width Visual Clean"
);
assert.match(
  cssSource,
  /\.final-review-prep-col\.is-hero|\.final-review-prep-stage[\s\S]{0,200}grid-template-columns/,
  "Prep stage must be a two-column professional grid"
);
assert.match(
  cssSource,
  /\.final-review--prep\s+\.final-review-prep-panel\s*\{[^}]*border:|\.final-review-prep-panel[\s\S]{0,200}border-radius:\s*1[24]px/,
  "Prep panels must use a soft professional studio shell"
);
assert.match(
  cssSource,
  /\.final-review-empty__step\.is-active|\.final-review-prep-journey[\s\S]{0,300}is-active|prep-stepper__item\.is-active|prep-steps__item\.is-active/,
  "Prep journey must highlight the active step"
);
assert.match(
  statesSource,
  /final-review-prep-steps|prep-steps__card|emptyStepLabelPrefix/,
  "Prep journey must use step cards with Step N prefix"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps\s*\{[^}]*flex-direction:\s*row/,
  "Prep steps must lay out Clean / Render / Compare on one horizontal row"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__item[\s\S]{0,160}flex-direction:\s*row/,
  "Each prep step keeps marker beside a slim passport-style card"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__marker[\s\S]{0,120}border-radius:\s*999px/,
  "Step markers must be circles"
);
assert.doesNotMatch(
  cssSource,
  /\.final-review-prep-steps__item:not\(:last-child\)::after[\s\S]{0,220}right:\s*-4px|\.final-review-prep-steps__item:not\(:last-child\)::after[\s\S]{0,220}left:\s*calc\(28px/,
  "Horizontal 3-up must not draw a connector line through the middle of step cards"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__item:not\(:last-child\)::after[\s\S]{0,280}width:\s*2px/,
  "Stacked narrow layout may keep a vertical marker rail between steps"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__progress|\.final-review-prep-steps__bar/,
  "Each step card must show a progress bar"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps\s*\{[^}]*width:\s*100%/,
  "Prep step rail must span full horizontal width"
);
assert.match(
  statesSource,
  /onAnalyze|onStartRender/,
  "Step cards must expose Analyze and Start render CTAs"
);
assert.match(
  statesSource,
  /prep-steps__desc|emptyStepDesc1/,
  "Each step card must show a short description"
);
assert.match(
  statesSource,
  /final-review-prep-steps__checkpoint[\s\S]*journeyAnalysisDone[\s\S]*journeyReviewCount/,
  "OCR review must replace fake percent progress with compact checkpoint states"
);
assert.match(
  cssSource,
  /\.final-review--prep \.final-review-prep-stage[\s\S]{0,100}align-items:\s*start/,
  "Locked First render panel must not stretch to the Visual Clean panel height"
);
assert.match(
  statesSource,
  /ocrWatchPaused|analyzePausedShort/,
  "Prep step Clean CTA must support a quiet Paused state (no Analyzing spinner)"
);
assert.match(
  statesSource,
  /renderWatchPaused|renderPausedShort|hideStartRenderCta/,
  "Prep Render CTA / First render panel must support pause controls and hide duplicate Rendering CTA"
);
assert.ok(en.finalReviewStates.renderWatchPaused, "EN must define render watch-paused copy");
assert.ok(en.finalReviewStates.renderPausedShort, "EN must define short Paused render label");
assert.ok(vi.finalReviewStates.renderWatchPaused, "VI must define render watch-paused copy");
assert.ok(vi.finalReviewStates.renderPausedShort, "VI must define short Paused render label");
assert.match(
  cssSource,
  /\.final-review-prep-steps__item\.is-locked|\.final-review-prep-steps__card\.is-locked/,
  "Locked step cards must have a distinct locked visual treatment"
);
assert.match(
  cssSource,
  /@keyframes\s+final-review-prep-step-in|@keyframes\s+fr-prep-step/,
  "Prep steps must define an entrance motion keyframe"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__item[\s\S]{0,200}animation:|\.final-review-prep-steps__item:nth-child/,
  "Prep step items must animate in (optionally staggered)"
);
assert.match(
  cssSource,
  /prefers-reduced-motion:\s*reduce[\s\S]{0,400}final-review-prep-steps/,
  "Prep step motion must disable under prefers-reduced-motion"
);
assert.ok(en.finalReviewStates.emptyStepLocked, "EN must define Locked step label");
assert.ok(vi.finalReviewStates.emptyStepLocked, "VI must define Locked step label");
assert.match(
  cssSource,
  /\.final-review-prep-steps__desc/,
  "CSS must style step card descriptions"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__card[\s\S]{0,120}flex-direction:\s*row/,
  "Passport-style step cards keep icon, title/progress, and CTA on one slim row"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__cta[\s\S]{0,200}width:\s*auto|\.final-review-prep-steps__cta[\s\S]{0,80}flex:\s*0\s+0\s+auto/,
  "Compact step CTAs must not stretch full card width"
);
assert.match(
  cssSource,
  /@media\s*\(max-width:\s*900px\)[\s\S]{0,500}\.final-review-prep-steps[\s\S]{0,160}flex-direction:\s*column|@media\s*\(max-width:\s*720px\)[\s\S]{0,500}\.final-review-prep-steps[\s\S]{0,160}flex-direction:\s*column/,
  "Narrow viewports must stack the three steps vertically again"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__cta[\s\S]{0,160}min-height:\s*(3[0-6])px/,
  "Step CTAs must stay compact and petite"
);
assert.doesNotMatch(
  cssSource,
  /\.final-review-prep-steps__cta\s+\.fr-tool__icon,\s*\n\s*\.final-review-prep-steps__cta\s+\.async-button__icon\s*\{\s*display:\s*none/,
  "Prep step CTAs (Start clean / Locked / …) must not hide leading icons on desktop"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__cta\s+\.async-button__icon|\.final-review-prep-steps__cta\s+\.fr-tool__icon/,
  "Prep step CTA icons must be styled (small glyph beside label)"
);
assert.match(
  statesSource,
  /empty__lock-badge[\s\S]{0,240}svg|lock-badge__icon/,
  "Up-next LOCKED badge must include a lock icon"
);
assert.match(
  statesSource,
  /cta\.is-locked[\s\S]{0,200}leadingIcon|locked \? \([\s\S]{0,120}svg[\s\S]{0,80}lock/,
  "Locked step pills must keep a lock leading icon"
);
assert.match(
  pageSource,
  /FinalReviewPrepJourney[\s\S]{0,800}onAnalyze|FinalReviewPrepJourney[\s\S]{0,800}onStartRender/,
  "Prep page must wire Analyze / Start render into the step list"
);
assert.match(
  pageSource,
  /ocrProgressPercent=\{ocrProgressPercent\}|renderProgressPercent=\{renderProgressPercent\}/,
  "Prep journey must receive live OCR/render job percents"
);
assert.ok(en.finalReviewStates.emptyStepLabelPrefix, "EN must define Step N: prefix");
assert.ok(en.finalReviewStates.emptyStepCta1, "EN must define Clean step CTA");
assert.ok(en.finalReviewStates.emptyStepCta3, "EN must define locked Compare CTA");
assert.ok(en.finalReviewStates.emptyStepDesc1, "EN must define Clean step description");
assert.ok(en.finalReviewStates.emptyStepDesc2, "EN must define Render step description");
assert.ok(vi.finalReviewStates.emptyStepDesc1, "VI must define Clean step description");
assert.ok(vi.finalReviewStates.emptyStepLabelPrefix, "VI must define Step N: prefix");
assert.doesNotMatch(
  visualSource,
  /className="pill warn"\s*>\s*\{t\("finalReviewVisual\.noCleaned"\)\}/,
  "Idle 'No cleaned video' must not use warn/orange tone"
);
assert.match(
  visualSource,
  /is-approve-quiet|approveQuiet/,
  "Approve must expose a quiet class when there is no cleaned output yet"
);
assert.match(
  statesSource,
  /WorkItemActionIcon[\s\S]*kind="process"|leadingIcon=\{<WorkItemActionIcon[\s\S]*kind="process"/,
  "Start render CTA must use the shared process icon"
);
assert.match(statesSource, /kind="transcript"/, "Prep Transcript link must use the shared transcript icon");
assert.match(statesSource, /kind="details"/, "Prep Review Board link must use the shared details icon");
assert.match(
  visualSource,
  /leadingIcon=\{<WorkItemActionIcon[\s\S]*kind="recheck"/,
  "Analyze OCR must use the shared recheck icon"
);
assert.match(
  visualSource,
  /leadingIcon=\{<WorkItemActionIcon[\s\S]*kind="approve"/,
  "Approve visual must use the shared approve icon"
);
assert.doesNotMatch(
  statesSource,
  /className="state-panel final-review-empty"/,
  "Empty state must leave the generic state-panel shell"
);
assert.doesNotMatch(
  pageSource,
  /final-review-preheader[\s\S]*fr-topbar__kicker|final-review-preheader--studio/,
  "Prep must not keep a studio preheader that duplicates shell Final Review chrome"
);
assert.match(
  statesSource,
  /emptyPrepHint|final-review-prep-briefing__hint/,
  "Prep briefing must keep a quiet next-step hint without a second page title"
);
assert.match(
  pageSource,
  /FinalReviewPrepBriefing|final-review-prep-briefing/,
  "Prep must show an outcome/context briefing so operators know the page goal"
);
assert.match(
  statesSource,
  /prepOutcomeGoal|prepContextOcr|prepOpenJobs|final-review-prep-briefing/,
  "Prep briefing must expose goal, OCR/render context, and Job Monitor link"
);
assert.match(
  cssSource,
  /\.final-review-prep-briefing/,
  "CSS must style the prep briefing strip"
);
assert.match(
  statesSource,
  /final-review-prep-briefing__phase-badge|final-review-prep-briefing__tile/,
  "Prep briefing must use phase badge + meta tiles instead of a flat pill dump"
);
assert.match(
  cssSource,
  /--fr-prep-shadow:|--fr-prep-gap:/,
  "Prep surfaces must share spacing and elevation tokens"
);
assert.match(
  cssSource,
  /--fr-prep-gap:\s*16px/,
  "Prep vertical rhythm gap must be 16px"
);
assert.match(
  cssSource,
  /--fr-prep-stage-gap:\s*18px/,
  "Dual prep panels must use an 18px stage gap so columns do not stick"
);
assert.match(
  cssSource,
  /\.final-review-prep-stage[\s\S]{0,160}gap:\s*var\(--fr-prep-stage-gap/,
  "Prep stage grid must consume the stage-gap token"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__item:not\(:last-child\)::after[\s\S]{0,80}content:\s*none/,
  "Desktop prep steps must explicitly disable the connector through cards"
);
assert.match(
  cssSource,
  /\.final-review--prep\s+\.final-review-prep-panel[\s\S]{0,200}padding:\s*20px\s+22px/,
  "Prep panels must use roomier padding"
);
assert.match(
  cssSource,
  /\.final-review--prep\s+\.final-review-prep-briefing[\s\S]{0,120}padding:\s*1[4-8]px/,
  "Prep briefing must leave air under the Operator Studio topbar"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__card[\s\S]{0,280}box-shadow:\s*var\(--fr-prep-shadow/,
  "Prep step cards must use the shared prep shadow"
);
assert.match(
  cssSource,
  /is-ocr-running|is-ocr-ready|is-ocr-partial/,
  "CSS must tone OCR/Render tiles by status"
);
assert.ok(en.finalReviewStates.prepPhaseBadgeClean, "EN must define short Clean phase badge");
assert.ok(en.finalReviewStates.prepPhaseBadgeRender, "EN must define short Render phase badge");
assert.ok(vi.finalReviewStates.prepPhaseBadgeClean, "VI must define short Clean phase badge");
assert.ok(en.finalReviewStates.prepOutcomeGoal, "EN must define prep outcome goal");
assert.ok(vi.finalReviewStates.prepOutcomeGoal, "VI must define prep outcome goal");
assert.ok(en.finalReviewStates.prepOpenJobs, "EN must define Job Monitor CTA");
assert.match(
  pageSource,
  /FinalReviewReadinessStrip|final-review-readiness/,
  "Workspace must show a readiness strip answering what is left for publish"
);
assert.match(
  pageSource,
  /loadFinalReviewChecklist|saveFinalReviewChecklist/,
  "Workspace checklist must persist per render in localStorage"
);
assert.match(
  previewSource,
  /resolveFinalReviewCompareDiff|final-review-compare-diff|compareDiff/,
  "Compare viewer must show original-vs-final diff meta"
);
assert.match(
  previewSource,
  /compare-diff__icon|CompareDiffIcon/,
  "Compare diff chips must use icons instead of long uppercase labels"
);
assert.match(
  previewSource,
  /final-review-compare-diff__item|title=\{t\(["']finalReviewStates\.compareDiff/,
  "Compare diff chips must keep full meaning via title tooltips"
);
assert.match(
  previewSource,
  /syncPlay|compare-sync|Link playback/,
  "Compare viewer must offer optional linked playback"
);
assert.match(
  previewSource,
  /compare-mode__icon|CompareToolbarIcon/,
  "Compare toolbar modes must include icons beside labels"
);
assert.match(
  previewSource,
  /compare-toolbar__modes|compare-toolbar__tools/,
  "Compare toolbar must separate mode segment from utility tools"
);
assert.ok(en.finalReviewStates.compareSideBySide.length <= 12, "EN side-by-side label must stay compact");
assert.ok(en.finalReviewStates.compareQuickSwitch.length <= 10, "EN quick-switch label must stay compact");
assert.ok(en.finalReviewStates.compareSyncOff.length <= 12, "EN link-playback label must stay compact");
assert.ok(en.finalReviewStates.readinessTitle, "EN must define readiness strip title");
assert.ok(en.finalReviewStates.readinessMissingPrefix, "EN must define missing-for-publish copy");
assert.ok(vi.finalReviewStates.readinessTitle, "VI must define readiness strip title");
assert.match(
  cssSource,
  /\.final-review--prep[\s\S]*\.final-review-prep-panel/,
  "Prep Final Review must style empty + visual panels as soft studio shells"
);
assert.match(
  cssSource,
  /\.final-review-prep-journey|\.final-review-empty__step/,
  "Prep must style the numbered journey rail"
);
assert.match(visualSource, /warnNoHardsub|warnCleanSkipped/, "Visual checkpoint must label no-hardsub warnings");
assert.match(
  visualSource,
  /priorCleanedKept|clean_skipped_no_hardsub/,
  "Visual checkpoint must not show green cleanedReady when this run skipped clean"
);
assert.match(
  visualSource,
  /showAllEvents|EVENTS_PREVIEW|slice\(0,\s*3\)/,
  "Visual events list must default to a short preview"
);
assert.doesNotMatch(
  visualSource,
  /visual_approved[\s\S]*pill good[\s\S]*approved/,
  "Visual rail must not duplicate Visual approved as a meta pill when CTA already shows it"
);
assert.match(
  pageSource,
  /analyzeNoOutput|clean_skipped_no_hardsub|no_hardsub_detected/,
  "Final Review must not claim analyzeSuccess when OCR produced no new cleaned video"
);
assert.ok(en.finalReviewVisual.warnNoHardsub.length > 0);
assert.ok(vi.finalReviewVisual.warnCleanSkipped.length > 0);
assert.ok(en.finalReviewVisual.analyzeNoOutput.length > 0);
assert.ok(vi.finalReviewVisual.priorCleanedKept.length > 0);
assert.ok(en.finalReviewHeader.rerender.length > 0 && en.finalReviewHeader.rerender.length <= 12);
assert.ok(vi.finalReviewHeader.transcriptEditor.length > 0 && vi.finalReviewHeader.transcriptEditor.length <= 12);
assert.ok(en.finalReviewHeader.publishDraft.length <= 10);
assert.ok(vi.finalReviewHeader.reviewBoard.length <= 12);
assert.ok(en.finalReviewVisual.showAllEvents.length > 0);
assert.ok(vi.finalReviewVisual.showAllEvents.length > 0);
assert.ok(en.finalReviewStates.startRender.length > 0);
assert.ok(en.finalReviewTabs.review.length > 0);
assert.match(
  pageSource,
  /FinalReviewRailIcon/,
  "Rail tabs must render icons for Review / Visual / Risk / Info"
);
assert.ok(en.finalReviewActions.checklistProgress.length > 0);
assert.ok(en.finalReviewActions.approveExport.length > 0 && en.finalReviewActions.approveExport.length <= 12);
assert.ok(en.finalReviewActions.markPublishReady.length > 0 && en.finalReviewActions.markPublishReady.length <= 14);
assert.ok(vi.finalReviewVisual.analyzeOcr.length > 0);
assert.ok(vi.finalReviewStates.startRender.length > 0);
assert.ok(vi.finalReviewTabs.review.length > 0);
assert.ok(vi.finalReviewActions.checklistProgress.length > 0);
assert.ok(vi.finalReviewActions.approveExport.length > 0 && vi.finalReviewActions.approveExport.length <= 12);
assert.ok(vi.finalReviewActions.markPublishReady.length > 0 && vi.finalReviewActions.markPublishReady.length <= 16);

assert.match(previewSource, /video-unavailable__icon/, "Unavailable compare media needs a designed visual empty state");
assert.match(
  cssSource,
  /\/\* Final Review V2 — polished approval workspace\. \*\//,
  "Final Review must keep its cohesive approval-workspace polish layer"
);
assert.match(
  cssSource,
  /\.final-review--workspace \.fr-review-chrome\s*\{[^}]*backdrop-filter:\s*blur\(14px\)[^}]*box-shadow:/s,
  "Header and readiness should share polished sticky chrome"
);
assert.match(
  cssSource,
  /\.final-review--workspace \.final-review-readiness__metric-value\s*\{[^}]*font-size:\s*1rem[^}]*font-weight:\s*740/s,
  "Readiness values should be easy to scan"
);
assert.match(
  cssSource,
  /\.final-review--workspace \.fr-stage\.compare-viewer\s*\{[^}]*border-radius:\s*16px[^}]*box-shadow:/s,
  "Compare viewer should use polished panel depth"
);
assert.match(
  cssSource,
  /\.final-review--workspace \.fr-stage__toolbar\.compare-toolbar\s*\{[^}]*background:\s*linear-gradient[^}]*border-radius:\s*11px/s,
  "Compare controls should sit in refined toolbar chrome"
);
assert.match(
  cssSource,
  /\.video-unavailable__icon\s*\{[^}]*height:\s*3rem[^}]*width:\s*3rem/s,
  "Unavailable video icon should have a deliberate visual frame"
);
assert.match(
  cssSource,
  /\.final-review--workspace \.fr-rail__tabs button\s*\{[^}]*flex-direction:\s*row[^}]*font-size:\s*0\.75rem/s,
  "Inspection tabs should use a compact horizontal icon-label layout"
);
assert.match(
  cssSource,
  /\.final-review--workspace \.fr-check__row\s*\{[^}]*border-radius:\s*9px[^}]*min-height:\s*38px/s,
  "Checklist rows should be compact interactive controls"
);
assert.match(
  cssSource,
  /\.final-review--workspace \.fr-decision-bar__actions button\.primary\s*\{[^}]*background:\s*linear-gradient[^}]*box-shadow:/s,
  "Publish-ready must remain the strongest decision action"
);
assert.match(
  readinessSource,
  /final-review-readiness__release|ReleaseReadinessIcon/,
  "Readiness should lead with one release outcome"
);
assert.doesNotMatch(
  readinessSource,
  /final-review-readiness__manifest-head/,
  "Approval Ribbon should not spend a separate row on a manifest heading"
);
assert.doesNotMatch(
  readinessSource,
  /final-review-readiness__score|--fr-release-progress|clearedGateCount/,
  "Micro Approval Bar should remove the oversized radial score"
);
assert.doesNotMatch(
  readinessSource,
  /final-review-readiness__release-eyebrow/,
  "Release Ledger should remove the repeated readiness eyebrow"
);
assert.match(
  readinessSource,
  /final-review-readiness__metric-dot/,
  "Release Ledger should use small status dots for supporting gates"
);
assert.doesNotMatch(
  readinessSource,
  /ReadinessGateIcon|final-review-readiness__metric-icon/,
  "Gate Deck should reserve detailed iconography for the main outcome"
);
assert.match(
  readinessSource,
  /gateChips[\s\S]*chip\.id === "checklist"[\s\S]*chip\.id === "warnings"[\s\S]*chip\.id === "risk"/,
  "Supporting gates should keep only checklist, warnings, and risk"
);
assert.match(
  readinessSource,
  /readinessChecklistLocal|readinessChipChecklistEvidence/,
  "Publish-ready renders should label missing local checklist evidence honestly"
);
assert.doesNotMatch(
  pageSource,
  /publish-ready-banner/,
  "Release Command Header should remove the duplicate publish-ready banner"
);
const gateDeckCss = cssSource.slice(cssSource.lastIndexOf("Final Review Gate Deck"));
assert.ok(gateDeckCss.length > 0, "Final Review must include the authoritative Gate Deck layer");
assert.match(
  gateDeckCss,
  /grid-template-areas:\s*"gates"\s*"release"/s,
  "Gate Deck should reverse the old hierarchy with gates above the decision"
);
assert.match(
  gateDeckCss,
  /\.final-review--workspace \.final-review-readiness--panel\s*\{[^}]*background:\s*transparent[^}]*border:\s*0[^}]*box-shadow:\s*none/s,
  "Gate Deck should remove the enclosing card shell"
);
assert.doesNotMatch(
  gateDeckCss,
  /conic-gradient|final-review-readiness__score-ring/,
  "Gate Deck should avoid radial decoration"
);
assert.match(
  gateDeckCss,
  /\.final-review--workspace \.final-review-readiness__gates\s*\{[^}]*gap:\s*8px[^}]*grid-area:\s*gates[^}]*grid-template-columns:\s*repeat\(3,/s,
  "Gate Deck should render three detached tiles above the decision"
);
assert.match(
  gateDeckCss,
  /\.final-review--workspace \.final-review-readiness__gates \.final-review-readiness__metric\s*\{[^}]*border-radius:\s*11px[^}]*box-shadow:/s,
  "Gate Deck tiles should feel independent and polished"
);
assert.match(
  gateDeckCss,
  /\.final-review--workspace \.final-review-readiness__release,[\s\S]*grid-area:\s*release[\s\S]*min-height:\s*52px/s,
  "Gate Deck should finish with a full-width compact decision bar"
);
assert.match(
  gateDeckCss,
  /@media \(max-width: 720px\)[\s\S]*\.final-review--workspace \.final-review-readiness__gates\s*\{[^}]*display:\s*flex[^}]*overflow-x:\s*auto/s,
  "Gate Deck should preserve its tile row with horizontal overflow on small screens"
);
assert.match(en.finalReviewStates.readinessAllClear, /cleared for publishing/i);
assert.match(vi.finalReviewStates.readinessAllClear, /sẵn sàng để publish/i);

console.log("final-review visual checkpoint tests passed");
