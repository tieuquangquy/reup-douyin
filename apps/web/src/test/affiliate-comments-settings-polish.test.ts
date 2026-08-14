/** Publishing Settings / Affiliate Comments: Intelligence worksheet polish. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/AffiliateCommentTemplatesSettingsPage.tsx"), "utf8");
const skeleton = readFileSync(resolve(webSrc, "components/operator-routes/IntelligenceDataSkeleton.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

assert.match(page, /OperatorStudioShell[\s\S]{0,220}?title=\{t\("publishingSettings\.affiliateComments"\)\}/, "Comments must use the leaf Affiliate Comments topbar title like Publication Library");
assert.match(page, /OperatorStudioShell[\s\S]{0,280}?description=\{t\("publishingSettings\.affiliateCommentsHint"\)\}/, "Comments must use its own topbar description");
assert.doesNotMatch(page, /OperatorStudioShell[\s\S]{0,280}?title=\{t\("affiliateCommentTemplates\.title"\)\}/, "Topbar must not use the template-list title; that belongs in the worksheet");
assert.doesNotMatch(page, /OperatorStudioShell[\s\S]{0,280}?title=\{t\("publishingSettings\.title"\)\}/, "Topbar must not use the shared Publishing Settings parent title");

assert.match(page, /CommentTemplateGlyph kind="plus"/, "New template must be icon-only like Catalog");
assert.match(page, /CommentTemplateGlyph kind="delete"/, "Delete must be icon-only");
assert.match(page, /aria-label=\{t\("affiliateCommentTemplates\.newTemplate"\)\}/, "New must keep an accessible name");
assert.match(page, /aria-label=\{t\("affiliateCommentTemplates\.delete"\)\}/, "Delete must keep an accessible name");
assert.match(page, /affiliate-comment-template-note/, "Errors must render as a worksheet note, not a floating danger banner");
assert.doesNotMatch(page, /className="inline-error"/, "Must not keep the generic inline-error banner");
assert.match(page, /affiliate-comment-template-editor__channel/, "FACEBOOK_REELS must be a mono channel footnote");
assert.match(page, /affiliate-comment-template-editor__body/, "Editor fields must live in one body grid");
assert.match(page, /affiliate-comment-template-editor__footer/, "Actions must use a dedicated footer hierarchy");
assert.match(page, /className="primary"[\s\S]{0,420}?affiliateCommentTemplates\.save/, "Save must remain the primary action");
assert.match(page, /affiliate-comment-template-list__row/, "Templates must render as dense scan rows, not nested cards with text delete");
assert.doesNotMatch(page, /affiliate-comment-template-card-delete/, "Retired text Delete button mark must go");
assert.match(page, /IntelligenceSplitEditorSkeleton/, "Cold-load must keep the shared split skeleton");

const cssStart = cssFull.indexOf("/* Publishing Settings Affiliate Comments v1");
assert.ok(cssStart >= 0, "v1 Affiliate Comments CSS block must exist");
const css = cssFull.slice(cssStart, cssStart + 14000);
assert.match(css, /--pl-iq-mint:\s*#f4f8f6/, "Comments worksheet must use Intelligence mint");
assert.match(css, /--pl-iq-label-strong:\s*#2a4d41/, "Comments worksheet must use Intelligence strong ink");
assert.match(css, /affiliate-comment-templates-page\.is-v1/, "v1 CSS must scope to the worksheet mark");
assert.match(css, /affiliate-comment-template-list__row/, "List rows must be styled as dense scan lines");
assert.match(css, /affiliate-comment-template-editor__footer/, "Footer hierarchy styles must exist");
assert.match(
  css,
  /affiliate-comment-template-note[\s\S]{0,420}?inset 2px 0 0 (?:#2a4d41|var\(--pl-iq-label-strong(?:,\s*#2a4d41)?\))/,
  "Note must use a strong ink spine",
);
assert.match(
  css,
  /publishing-settings-page\.is-v1\.is-v4:has\(\.affiliate-comment-templates-page\.is-v1\)/,
  "Settings shell must expand for the Comments worksheet like Catalog",
);
assert.match(
  css,
  /publishing-settings-page\.is-v1\.is-v4:has\(\.affiliate-comment-templates-page\.is-v1\)\s*\{[\s\S]{0,220}?padding:\s*18px\s+var\(--app-content-inset-x\)/,
  "Comments stack must share the topbar horizontal inset like Catalog / Content AI",
);
assert.match(
  css,
  /publishing-settings-page\.is-v1\.is-v4:has\(\.affiliate-comment-templates-page\.is-v1\)\s*\{[\s\S]{0,220}?gap:\s*18px/,
  "Nav-to-worksheet gap must match Catalog / Content AI (18px)",
);

assert.match(
  page,
  /leadingIcon=\{<CommentTemplateGlyph kind="save" \/>\}[\s\S]{0,220}?onClick=\{\(\) => void save\(\)\}/,
  "Save must use a leading save glyph",
);
assert.match(
  page,
  /leadingIcon=\{<CommentTemplateGlyph kind="check" \/>\}[\s\S]{0,220}?onClick=\{\(\) => void save\(true\)\}/,
  "Save & Activate must use a leading check glyph",
);
assert.match(
  page,
  /leadingIcon=\{<CommentTemplateGlyph kind="check" \/>\}[\s\S]{0,280}?onClick=\{\(\) => void activate/,
  "Activate must use a leading check glyph",
);
assert.match(
  css,
  /affiliate-comment-template-list > header \{\s*align-items:\s*center/,
  "List header title and New button must vertically center",
);
assert.match(
  css,
  /affiliate-comment-template-editor__footer[\s\S]{0,280}?affiliate-comment-template-glyph[\s\S]{0,80}?0\.9rem/,
  "Footer glyphs must sit at 0.9rem inside the action buttons",
);

assert.match(skeleton, /pl-iq-data-skeleton is-split/, "Shared split skeleton mark must remain");

console.log("affiliate-comments-settings-polish: PASS");
