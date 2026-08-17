/**
 * Publish Draft detail desk — opened draft (not the index poster).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  remainingHashtagSlots,
  remainingPostChars,
  resolvePublishAccountId
} from "../lib/publishDraftState";
import type { EditablePublishDraft, PublishTarget } from "../types/publish-draft";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const page = readFileSync(resolve(webSrc, "components/publish-draft/PublishDraftPage.tsx"), "utf8");
const header = readFileSync(resolve(webSrc, "components/publish-draft/PublishDraftHeader.tsx"), "utf8");
const caption = readFileSync(resolve(webSrc, "components/publish-draft/CaptionEditor.tsx"), "utf8");
const hashtag = readFileSync(resolve(webSrc, "components/publish-draft/HashtagEditor.tsx"), "utf8");
const selector = readFileSync(resolve(webSrc, "components/publish-draft/PublishTargetSelector.tsx"), "utf8");
const destSelect = readFileSync(resolve(webSrc, "components/publish-draft/PublishDestSelect.tsx"), "utf8");
const schedule = readFileSync(resolve(webSrc, "components/publish-draft/PublishSchedulePanel.tsx"), "utf8");
const gate = readFileSync(resolve(webSrc, "components/publish-draft/PublishDraftGate.tsx"), "utf8");
const preview = readFileSync(resolve(webSrc, "components/publish-draft/PublishPreviewPanel.tsx"), "utf8");
const shell = readFileSync(resolve(webSrc, "components/operator-routes/OperatorPublishDraftPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8")) as {
  publishDraftPage: Record<string, string>;
  publishDraftHeader: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8")) as {
  publishDraftPage: Record<string, string>;
  publishDraftHeader: Record<string, string>;
};

const target: PublishTarget = {
  platform: "TIKTOK",
  label: "TikTok",
  caption_max_length: 100,
  hashtag_limit: 3,
  supports_scheduling: true,
  account_ref_required: false
};
const editable: EditablePublishDraft = {
  id: "draft-1",
  targetPlatform: "TIKTOK",
  platformAccountRef: "",
  title: "Video title",
  caption: "Hello world",
  ctaText: "Watch",
  hashtags: [{ tag: "one", source: "default" }],
  languageCode: "vi",
  platformNotes: "",
  schedulingNotes: "",
  notes: "",
  plannedPublishAt: "",
  timezone: "Asia/Bangkok"
};

assert.equal(remainingPostChars(editable, target), 100 - "Hello world\n\nWatch\n\n#one".length);
assert.equal(remainingHashtagSlots(editable, target), 2);
assert.equal(remainingPostChars(editable, null), null);

assert.equal(
  resolvePublishAccountId("acct-assigned", [{ id: "acct-a" }, { id: "acct-assigned" }], "acct-a"),
  "acct-assigned"
);
assert.equal(
  resolvePublishAccountId(null, [{ id: "acct-a" }, { id: "acct-b" }], "acct-b"),
  "acct-b"
);
assert.equal(resolvePublishAccountId("missing", [{ id: "acct-a" }], ""), "");
assert.equal(resolvePublishAccountId(null, [{ id: "acct-a" }], ""), "");

assert.match(page, /publish-draft-desk/, "Detail must use the opened-draft desk shell");
assert.match(page, /publish-draft-desk__strip|PublishDraftHeader/, "Identity strip must stay on the desk");
assert.match(page, /publish-draft-desk__copy/, "Copy canvas must be a named region");
assert.match(page, /publish-draft-desk__rail/, "Destination/risk/dispatch must live on a rail");
assert.match(page, /assigned_platform_account_id/, "Publish destination must read assignment authority");
assert.match(page, /resolvePublishAccountId/, "Account select must prefer the assigned account over accounts[0]");
assert.match(page, /publishDraftPage\.unassignedAccount/, "Unassigned drafts must show an empty account choice, not auto-fill the first page");
assert.doesNotMatch(
  page,
  /fetchPlatformAccounts\("FACEBOOK_REELS"\)/,
  "Account list must follow the draft platform, not a hardcoded Facebook Reels query"
);
assert.match(page, /error_message/, "FAILED / needs-attention drafts must surface error_message");
assert.match(page, /remainingPostChars|remainingHashtagSlots/, "Strip must show remaining platform limits");
assert.match(page, /published_at/, "Published outcome must surface published_at from draft/summary");
assert.doesNotMatch(
  page,
  /<details[\s\S]{0,280}publish-draft-desk__notes|<details className="publish-draft-desk__notes"/,
  "Notes must stay expanded, not a collapsed details"
);
assert.doesNotMatch(
  page,
  /<details[\s\S]{0,120}publish-draft-desk__attempts|<details className="publish-draft-desk__attempts"/,
  "Attempts must stay expanded, not a collapsed details"
);
assert.match(page, /publish-draft-desk__notes/, "Notes remain a named desk region");
assert.match(page, /publish-draft-desk__attempts/, "Attempts remain a named dest region");
assert.match(
  page,
  /publish-draft-desk__attempts-empty/,
  "Empty attempts must sit in a named empty well, not a stray muted line"
);
assert.match(page, /publish-draft-desk__attempts-head/, "Attempts header must share dest chip rhythm, not a hamburger label");
assert.doesNotMatch(
  page,
  /d="M4\.6 5\.4h10\.8M4\.6 10h10\.8M4\.6 14\.6h7\.2"/,
  "Attempts must not use a hamburger icon that reads as a menu"
);
assert.match(
  css,
  /\.publish-draft-desk__tagbar[\s\S]{0,80}border-radius/,
  "Empty attempts well must reuse the hashtag tagbar mint inset"
);
assert.match(header, /publish-draft-desk__title|id="publish-draft-title"/, "Title must be an editable field on the strip");
assert.match(
  header,
  /publish-draft-desk__actions[\s\S]{0,220}publish-draft-desk__jumps[\s\S]{0,400}nav\.finalReview[\s\S]{0,400}nav\.publishDrafts[\s\S]{0,400}publish-draft-desk__ops[\s\S]{0,800}publishDraftHeader\.discard/,
  "Final Review / Drafts sit in a jump rail beside a compact ops cluster, still on one strip row"
);
assert.match(
  header,
  /href=\{`\/production\/final-review\/\$\{sourceVideoId\}`\}/,
  "This video's Final Review jump lives on the strip, not the workspace header"
);
assert.match(header, /href="\/publishing\/drafts"/, "All drafts lives on the strip, not the workspace header");
assert.match(
  css,
  /\.publish-draft-desk__jumps\s*\{[\s\S]{0,160}display:\s*inline-flex/,
  "Workflow jumps share one segmented rail instead of six equal pills"
);
assert.match(
  css,
  /\.publish-draft-desk__ops\s*\{[\s\S]{0,80}display:\s*inline-flex/,
  "Save / ready / publish stay a tight ops cluster"
);
assert.match(
  css,
  /\.publish-draft-desk__actions \.publish-draft-desk__action[\s\S]{0,220}min-height:\s*3[0-4]px/,
  "Strip verbs must sit shorter than dest command buttons"
);
assert.doesNotMatch(
  page,
  /publish-draft-desk__mast/,
  "Preparation must stay one strip card, not a mast wrapping a leftover jump row"
);
assert.doesNotMatch(
  caption,
  /internalNotes|editable\.notes/,
  "Internal notes must leave the caption canvas"
);
assert.match(shell, /OperatorStudioShell/, "Detail must stay in Operator Studio");
assert.match(shell, /TopbarRefreshButton/, "Detail must keep Refresh in the Topbar like other Operator pages");
assert.doesNotMatch(
  shell,
  /nav\.finalReview|nav\.publishDrafts/,
  "Final Review and Drafts must leave the workspace header"
);
assert.match(shell, /PublishDraftPageHandle|useRef/, "Shell must call into the publish-draft refresh handle");
assert.match(page, /useImperativeHandle|forwardRef/, "Publish draft must expose an imperative refresh handle");
assert.match(
  page,
  /mode:\s*"initial"\s*\|\s*"refresh"|mode === "refresh"/,
  "Refresh must reload quietly without a full-page loading flash"
);
assert.doesNotMatch(page, /is-poster|is-pass|OpsSummaryCards|ops-drafts-kpi/, "Index poster / ticket / KPI chrome must stay off this desk");
assert.doesNotMatch(page, /cookie|secret|token/i, "Desk must not render credential fields");
assert.match(css, /\.publish-draft-desk\s*\{/, "Desk layout must be styled");
assert.match(css, /\.publish-draft-desk__copy/, "Copy canvas must have layout CSS");
assert.match(css, /\.publish-draft-desk__rail/, "Rail must have layout CSS");
assert.match(
  page,
  /publish-draft-desk__rail[\s\S]*PublishPreviewPanel/,
  "Post compose must sit on the rail, not below the copy canvas"
);
assert.doesNotMatch(
  page,
  /publish-draft-desk__copy[\s\S]*PublishPreviewPanel[\s\S]*publish-draft-desk__rail/,
  "Left copy column must not keep a trailing preview void"
);
assert.doesNotMatch(
  selector,
  /accountRefPlaceholder|local-account-1/,
  "Account-ref stub must leave the platform bar"
);
assert.match(
  page,
  /humanizeStatus\(draft\.target_platform\)/,
  "Destination platform must read draft.target_platform, not Unknown publication status"
);
assert.match(
  preview,
  /publish-draft-desk__compose/,
  "Preview must render as a compose frame, not a disconnected dark dump"
);
assert.match(css, /\.publish-draft-desk__compose/, "Compose frame must be styled");
assert.match(
  css,
  /\.publish-draft-desk__phone|\.publish-draft-desk__compose-video/,
  "Compose must show the approved render in a phone-proportion frame"
);
assert.match(page, /publish-draft-desk is-stage/, "Desk must mark the reel-stage composition");
assert.match(
  preview,
  /publish-draft-desk__phone-meta[\s\S]*publish-draft-desk__phone-avatar[\s\S]*accountLabel[\s\S]*publish-draft-desk__phone-copy[\s\S]*publish-draft-desk__phone[\s\S]*compose-video/,
  "Rail reads as a feed post: page identity, caption, then 9:16 video"
);
assert.match(
  preview,
  /publishPreviewPanel\.justNow[\s\S]*publishPreviewPanel\.visibilityPublic/,
  "Page row shows preview freshness and public visibility, not dest kickers"
);
assert.match(
  preview,
  /publish-draft-desk__phone-react[\s\S]*publish-draft-desk__phone-react-icon[\s\S]*publishPreviewPanel\.like[\s\S]*publish-draft-desk__phone-react-icon[\s\S]*publishPreviewPanel\.comment[\s\S]*publish-draft-desk__phone-react-icon[\s\S]*publishPreviewPanel\.share/,
  "Feed footer pairs dest-style icons with like/comment/share labels"
);
assert.doesNotMatch(
  preview,
  /publish-draft-desk__phone-react[\s\S]*onClick|publish-draft-desk__phone-react[\s\S]*<button/,
  "Feed reactions must not be live actions"
);
assert.match(
  page,
  /accountLabel=\{selectedAccount\?\.display_name \?\? t\("publishDraftPage\.unassignedAccount"\)\}/,
  "Rail page name must follow dest selected account, not a leftover Unknown"
);
assert.doesNotMatch(
  preview,
  /publish-draft-desk__phone-overlay/,
  "Video stage must not paint caption over the approved render"
);
assert.doesNotMatch(
  preview,
  /publish-draft-desk__reel-copy/,
  "Live reel overlay copy must stay off the face"
);
assert.match(
  preview,
  /publish-draft-desk__phone-copy[\s\S]{0,160}preview \|\| t\("publishPreviewPanel\.placeholder"\)/,
  "Rail shows the composed caption or the empty placeholder"
);
assert.match(
  css,
  /\.publish-draft-desk__rail[\s\S]{0,80}order:\s*-1|\.publish-draft-desk__stage[\s\S]{0,180}grid-template-areas/,
  "Reel stage must lead the layout (rail first), editor docks beside it"
);
assert.match(page, /publish-draft-desk__dock/, "Caption + tags must share one writing dock");
assert.match(css, /\.publish-draft-desk__dock/, "Writing dock must be styled as a single surface");
assert.match(
  css,
  /\.publish-draft-desk__copy[\s\S]{0,160}align-content:\s*start/,
  "Copy column must not stretch empty white panels beside the phone"
);
assert.match(
  css,
  /\.publish-draft-desk__title[\s\S]{0,220}text-overflow:\s*ellipsis/,
  "Strip title must truncate instead of filling the bar with the whole caption"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__phone-meta[\s\S]{0,220}align-items:\s*center/,
  "Feed identity sits as a post header, not dest ACCOUNT kickers"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__phone-react[\s\S]{0,220}align-items:\s*center/,
  "Like/comment/share sit as icon+label rows, not bare text"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__phone-copy[\s\S]{0,220}max-height:\s*5\.2rem/,
  "Feed caption must expand to full copy, not a scroll well"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__phone-copy[\s\S]{0,220}overflow:\s*visible/,
  "Feed caption must not clip behind a scrollbar"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__phone-copy[\s\S]{0,160}background:\s*transparent/,
  "Feed caption sits on post paper, not a mint tagbar or dark overlay"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__phone-copy[\s\S]{0,200}position:\s*absolute/,
  "Rail caption must not sit on the video stage"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__compose[\s\S]{0,220}width:\s*100%/,
  "Feed card fills the rail; 9:16 applies to the video, not the whole post"
);
assert.match(header, /function PublishStripIcon/, "Strip must own verb icons instead of borrowing queue glyphs");
assert.match(header, /kind="discard"/, "Discard must have a revert icon");
assert.match(header, /kind="save"/, "Save draft must have a save icon");
assert.match(header, /kind="ready"/, "Mark ready must have an approve icon");
assert.match(header, /kind="publish"/, "Publish now must have a send icon");
assert.match(header, /leadingIcon=\{<PublishStripIcon/, "Async strip actions must pass the icon into AsyncButton");
assert.match(css, /\.publish-draft-desk__action\s*\{/, "Strip actions must share one icon+label chrome");
assert.match(css, /\.publish-draft-desk__chip\.is-ready/, "Ready status chip must read as a pass signal, not another grey pill");
assert.match(
  css,
  /\.publish-draft-desk__heading\s*\{[\s\S]{0,220}text-transform:\s*none/,
  "Card titles are forest headings, not all-caps mint pills"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk__heading\s*\{[\s\S]{0,200}background:\s*color-mix/,
  "Card titles must not reuse the dest chip mint fill"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk__label\s*\{[\s\S]{0,220}border-radius:\s*999px/,
  "Field names are form labels, not a second mint pill"
);
assert.match(
  css,
  /\.publish-draft-desk__chip\.is-ready[\s\S]{0,180}background:\s*color-mix\(in srgb, #2f8f6f 10%/,
  "Clear-gate chip must not be a second, denser mint than kickers"
);
assert.match(
  css,
  /\.publish-draft-desk \.hashtag-list button[\s\S]{0,220}border:\s*1px solid color-mix\(in srgb, #2f8f6f 22%/,
  "Hashtag pills must use the dest chip outline"
);
assert.match(
  caption,
  /publish-draft-desk__copy-head[\s\S]{0,280}publish-draft-desk__heading[\s\S]{0,400}captionEditor\.title/,
  "Caption title is a forest heading plus remaining chip, not a mint pill"
);
assert.match(
  caption,
  /publish-draft-desk__label[\s\S]{0,80}captionEditor\.cta/,
  "CTA uses a form label, not a mint pill"
);
assert.match(
  caption,
  /publish-draft-desk__label[\s\S]{0,80}id="caption-language-label"/,
  "Language uses a form label beside the vi chip"
);
assert.match(
  page,
  /publish-draft-desk__attempts-head[\s\S]{0,120}publish-draft-desk__heading/,
  "Attempts title is a forest heading plus count chip"
);
assert.match(
  page,
  /publish-draft-desk__label[\s\S]{0,80}captionEditor\.internalNotes/,
  "Notes fields use form labels, not mint pills"
);
assert.match(
  caption,
  /publish-draft-desk__chip[\s\S]{0,120}remainingChars/,
  "Caption remaining chars sit on the card header like dest Unassigned"
);
assert.match(
  hashtag,
  /publish-draft-desk__copy-head[\s\S]{0,280}publish-draft-desk__heading[\s\S]{0,200}hashtagEditor\.title/,
  "Hashtags title is a forest heading above the tagbar"
);
assert.doesNotMatch(hashtag, /publish-draft-desk__kicker/, "Hashtags must leave the mint kicker pills");
assert.match(
  hashtag,
  /publish-draft-desk__chip\$\{remainingTags < 0 \? " is-warn" : " is-ready"\}/,
  "Hashtag remaining uses dest count chip, not a ghost quiet label"
);
assert.match(
  page,
  /publish-draft-desk__notes-head[\s\S]{0,200}publish-draft-desk__heading[\s\S]{0,120}publishDraftPage\.notes/,
  "Notes title is a forest heading, not a mint pill"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__copy-head[\s\S]{0,220}justify-content:\s*space-between/,
  "Caption header must reuse dest bay-head alignment"
);
assert.match(hashtag, /publish-draft-desk__add/, "Add hashtag must use the compact icon control");
assert.doesNotMatch(
  hashtag,
  />\s*\{t\("hashtagEditor.add"\)\}\s*</,
  "Add must not keep a visible text label beside the icon"
);
assert.match(css, /\.publish-draft-desk__add\s*\{/, "Add icon control must be sized as a square action");
assert.match(page, /publish-draft-desk__dock is-pedestal/, "Writing dock must share dest pedestal chrome");
assert.doesNotMatch(page, /publish-draft-desk__dock is-notebook/, "Caption must leave the notebook modifier");
assert.match(selector, /publish-draft-desk__channel/, "Platform must sit in a channel chip, not a nested form box");
assert.match(hashtag, /publish-draft-desk__tagbar/, "Pills and add must share one tag well");
assert.match(css, /\.publish-draft-desk__channel\s*\{/, "Channel chip must be styled");
assert.match(css, /\.publish-draft-desk__tagbar\s*\{/, "Tag well must be styled");
assert.match(
  css,
  /dock\.is-pedestal[\s\S]{0,420}textarea[\s\S]{0,120}background:\s*transparent/,
  "Caption must write on dest paper, not inside a second grey box"
);
assert.match(page, /publish-draft-desk__bay/, "Destination must be a dispatch bay, not a leftover form card");
assert.match(page, /function PublishBayIcon/, "Bay actions must own verb icons");
assert.match(
  page,
  /publish-draft-desk__bay-head[\s\S]*is-\$\{assignmentStatus\.toLowerCase\(\)\}/,
  "Unassigned must sit on the Destination header, not an extra field row"
);
assert.match(page, /leadingIcon=\{<PublishBayIcon kind="reconcile"/, "Reconcile must show a sync icon");
assert.match(page, /publish-draft-desk__account/, "Account select must sit in a named well");
assert.match(css, /\.publish-draft-desk__bay\s*\{/, "Destination bay must be styled");
assert.match(
  css,
  /\.publish-draft-desk__chip\.is-unassigned/,
  "Unassigned must not share the mint pass treatment"
);
assert.match(
  page,
  /publish-draft-desk__rail[\s\S]*PublishPreviewPanel[\s\S]*publish-draft-desk__bay/,
  "Destination must sit under the reel, not as another white card in the copy stack"
);
assert.doesNotMatch(
  page,
  /publish-draft-desk__dock[\s\S]*publish-draft-desk__bay[\s\S]*publish-draft-desk__rail/,
  "Bay must leave the notebook column"
);
assert.match(page, /publish-draft-desk__bay is-pedestal/, "Bay must mark the phone pedestal treatment");
assert.match(
  css,
  /\.publish-draft-desk__bay\.is-pedestal[\s\S]{0,220}inset 4px 0 0 #2a4d41/,
  "Dest card must use Operator Studio forest spine on a light surface"
);
assert.match(
  css,
  /\.publish-draft-desk__bay\.is-pedestal[\s\S]{0,160}background:\s*#fff/,
  "Dest must share the worksheet paper fill, not an inverted forest fill"
);
{
  const copyStart = page.indexOf('className="publish-draft-desk__copy"');
  const railStart = page.indexOf('className="publish-draft-desk__rail"');
  const bayStart = page.indexOf("publish-draft-desk__bay is-pedestal");
  const copyRegion = page.slice(copyStart, railStart > copyStart ? railStart : bayStart);
  assert.doesNotMatch(
    copyRegion,
    /PublishSchedulePanel/,
    "Schedule must not stack as a leftover form card beside the notebook"
  );
  assert.doesNotMatch(
    copyRegion,
    /PublishMediaSummary/,
    "Media facts must not duplicate the phone as a second white card"
  );
  assert.doesNotMatch(
    copyRegion,
    /RiskSummaryCard/,
    "Copy column must not render the Final Review risk decision bar"
  );
  assert.doesNotMatch(
    copyRegion,
    /publish-draft-desk__dock[\s\S]*PublishTargetSelector/,
    "Opened-draft notebook must not repeat the platform selector"
  );
  assert.doesNotMatch(
    copyRegion,
    /publish-draft-desk__notes/,
    "Notes must leave the copy column so caption → account is not interrupted"
  );
}
assert.doesNotMatch(page, /RiskSummaryCard|fr-risk__decisions/, "Publish desk must not reuse FR Continue/Needs fix/Reject/Approve chrome");
assert.match(
  page,
  /is-pedestal[\s\S]*PublishSchedulePanel/,
  "When/schedule must sit on the phone pedestal with destination"
);
assert.match(
  page,
  /is-pedestal[\s\S]*PublishTargetSelector/,
  "Opened-draft platform must live on dest, not a second channel in the notebook"
);
assert.match(page, /publish-draft-desk__gate/, "Risk must collapse to a send-gate chip, not a panel");
assert.match(css, /\.publish-draft-desk__gate\s*\{/, "Send-gate chip must be styled on the pedestal");
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__stage[\s\S]{0,280}grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(/,
  "Stage columns fill the strip: paper grows, phone stays a feed rail"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__stage[\s\S]{0,220}width:\s*100%/,
  "Compose pair shares the strip width, not a centered island"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__stage[\s\S]{0,420}grid-template-columns:\s*minmax\(26rem,\s*42rem\)/,
  "Stage must not cap the paper column at 42rem under a full-width strip"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__stage[\s\S]{0,360}grid-template-areas/,
  "Stage must place the three blocks with named areas, not a leftover two-column stack"
);
assert.match(
  css,
  /grid-template-areas:[\s\S]{0,80}"paper phone"[\s\S]{0,80}"dest phone"[\s\S]{0,80}"notes phone"/,
  "Composer frame: caption, dest, then notes; sticky phone on the right"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__rail[\s\S]{0,200}position:\s*sticky/,
  "Phone preview must stay in view while the operator fills the left cards"
);
assert.match(
  page,
  /publish-draft-desk__rail[\s\S]*PublishPreviewPanel[\s\S]*<\/aside>[\s\S]*publish-draft-desk__copy[\s\S]*publish-draft-desk__bay is-pedestal[\s\S]*publish-draft-desk__notes/,
  "Phone, paper, dest, then notes must be stage siblings"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__notes[\s\S]{0,160}grid-area:\s*notes/,
  "Notes must occupy the stage notes area under destination"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__notes[\s\S]{0,280}max-width:\s*none/,
  "Notes fills the same paper track as caption and dest"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__copy[\s\S]{0,200}max-width:\s*none/,
  "Caption paper fills the paper track under the strip"
);
assert.match(
  css,
  /\.publish-draft-desk__bay\.is-pedestal[\s\S]{0,280}max-width:\s*none/,
  "Pedestal must be a stand wider than the phone, not a cloned 9:16 strip"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal[\s\S]{0,240}min-height:\s*12rem/,
  "Caption pedestal must read as a writing card, not a stretched void"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal[\s\S]{0,280}inset 4px 0 0 #2a4d41/,
  "Caption pedestal must share the forest spine with dest and notes"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal[\s\S]{0,220}padding:\s*10px 20px/,
  "Caption pedestal inset must match dest, not the tighter notebook pad"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal \.publish-draft-desk__copy-block textarea[\s\S]{0,220}font-size:\s*1\.02rem/,
  "Caption writes at dest platform size, not leftover 0.95rem form type"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal \.publish-panel[\s\S]{0,160}padding:\s*0/,
  "Inner composer panels must not add a second notebook pad on dest pedestal"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal \.publish-draft-desk__add[\s\S]{0,240}background:\s*color-mix\(in srgb, #2f8f6f 10%/,
  "Add plus uses dest chip mint, not a leftover forest square"
);
assert.match(
  caption,
  /publish-draft-desk__chip\$\{remainingChars < 0 \? " is-warn" : " is-ready"\}/,
  "Caption remaining uses dest count chip, not a ghost quiet label"
);
assert.match(
  css,
  /\.publish-draft-desk__tagbar[\s\S]{0,80}background:\s*#f4f8f6/,
  "Tag well remains the recessed mint authority"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal \.publish-draft-desk__lang input[\s\S]{0,280}background:\s*color-mix\(in srgb, #2f8f6f 10%/,
  "Language vi uses the dest chip fill, not a leftover grey form box"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dock\.is-pedestal \.publish-draft-desk__lang input[\s\S]{0,280}border-radius:\s*999px/,
  "Language vi must be a dest chip, not a 10px form control"
);
assert.match(
  css,
  /\.publish-draft-desk__dock\.is-pedestal \.publish-draft-desk__cta\s*\{[\s\S]{0,160}background:\s*transparent/,
  "CTA text sits on dest paper beside the field label, not inside one fused mint pill"
);
assert.match(
  css,
  /\.publish-draft-desk__dock\.is-pedestal \.publish-draft-desk__tags[\s\S]{0,80}padding:\s*4px 0/,
  "Hashtag well uses dest card inset, not a second 20px notebook pad"
);
assert.match(
  schedule,
  /planned_publish_at \? ["']is-ready["'] : ["']is-unassigned["']/,
  "Unscheduled must use the same tan chip as Unassigned"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-sheet\s*\{[\s\S]{0,160}background:\s*(transparent|#fff)/,
  "Dest sheet must be notebook paper, not a second mint card around platform/account/time"
);
assert.match(
  page,
  /publish-draft-desk__dest-identity[\s\S]*publish-draft-desk__route[\s\S]*publish-draft-desk__account/,
  "Platform and account stay stacked on dest paper like caption then CTA"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-identity[\s\S]{0,160}display:\s*grid/,
  "Dest identity stacks like the notebook, not a display:contents dateline"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk__dest-identity[\s\S]{0,120}display:\s*contents/,
  "Identity must paint as a notebook stack, not leak into a newspaper grid"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dest-sheet[\s\S]{0,280}grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  "Dest sheet is one notebook column, matching Caption and Notes"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-sheet \.publish-draft-desk__when[\s\S]{0,180}border-top/,
  "Time splits with the same notebook hairline as the Caption CTA row"
);
assert.match(
  page,
  /publish-draft-desk__cta-row[\s\S]{0,280}publish-draft-desk__label[\s\S]{0,120}publishDraftPage\.destinationAccount[\s\S]{0,180}id="platform-account"/,
  "Publish account uses a form label beside the picker, not a mint pill"
);
assert.doesNotMatch(
  page,
  /publish-draft-desk__dest-account[\s\S]{0,220}publish-draft-desk__dest-eyebrow/,
  "Account must not spend a dest eyebrow above the picker"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dest-sheet \.publish-draft-desk__when-stamp[\s\S]{0,280}display:\s*flex/,
  "Planned time sits in one dest stamp row, not a 3-cell spreadsheet"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dest-sheet \.publish-draft-desk__when-stamp > label[\s\S]{0,220}flex:\s*1/,
  "Date/time/timezone share dest width like platform and account, not leftover chips on the left"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dest-sheet \.publish-draft-desk__when-stamp input[\s\S]{0,200}max-width:\s*none/,
  "Stamp inputs must fill their dest cell, not freeze at 12rem"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dest-sheet \.publish-draft-desk__when-stamp[\s\S]{0,280}grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)/,
  "Stamp must not flatten date/time/timezone into equal spreadsheet cells"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dest-sheet \.publish-draft-desk__when-stamp > label:not\(:first-child\)[\s\S]{0,160}border-left/,
  "Stamp pills must wrap like hashtags, not split with vertical hairlines"
);
assert.match(
  css,
  /\.publish-draft-desk__attempts-empty[\s\S]{0,200}border:\s*1px dashed/,
  "Empty attempts sits in a dashed well like the dest spec"
);
assert.doesNotMatch(
  schedule,
  /className="publish-draft-desk__action is-quiet"/,
  "Unschedule is a bordered dest card, not ghost text"
);
assert.doesNotMatch(
  page,
  /className="publish-draft-desk__action is-quiet"[\s\S]{0,240}reconcileDraft/,
  "Reconcile draft is a bordered dest card beside Unschedule"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk__command \.publish-draft-desk__action\.is-schedule[\s\S]{0,260}max-width:\s*1[3-6]\.[0-9]+rem/,
  "Schedule must span dest like other desk primaries, not a floating send pill"
);
assert.doesNotMatch(
  schedule,
  /visually-hidden[\s\S]{0,80}publishSchedulePanel\.plannedPublishTime/,
  "Planned publish time is a visible notebook label, not a hidden dateline caption"
);
assert.match(
  css,
  /\.publish-draft-desk__when-stamp\s*\{[\s\S]{0,180}background:\s*#f4f8f6/,
  "Planned time stamp must be a tagbar-sized well on white paper"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__note textarea[\s\S]{0,140}background:\s*#f4f8f6/,
  "Notes fields must keep the recessed mint well"
);
assert.match(
  css,
  /\.publish-draft-desk__scan\s*\{[\s\S]{0,180}background:\s*transparent/,
  "Risk scan must sit on dest paper like the CTA row, not another mint nest"
);
assert.match(
  css,
  /\.publish-draft-desk__scan-head[\s\S]{0,280}grid-template-columns:\s*auto\s+auto/,
  "Risk status must stay a compact chip beside Run risk check, not a 1fr mint slab"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__bay\.is-pedestal \.publish-draft-desk__dest-sheet \.publish-draft-desk__dest-hero[\s\S]{0,220}background:\s*transparent/,
  "Platform writes on dest paper like Caption, not a filled mint select well"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-picker \.publish-draft-desk__channel-row[\s\S]{0,80}flex:\s*1 1 auto/,
  "Account chevron anchors to the well edge, not the Unassigned label width"
);
assert.doesNotMatch(
  css,
  /\.publish-draft-desk__dest-picker\s*\{[^}]*z-index:\s*[1-9]/,
  "Closed dest pickers must not each create a stacking lid over later dest rows"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-picker\.is-open[\s\S]{0,140}z-index:\s*(?:[8-9]|[1-9]\d)/,
  "Open dest menu must stack above the account row and time stamp"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__dest-sheet \.publish-draft-desk__dest-account[\s\S]{0,200}(?:flex-direction:\s*column|display:\s*grid)/,
  "Account is a dest TIME stack: label then picker, not a squeezed inline row"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__bay\.is-pedestal \.publish-draft-desk__dest-account \.publish-draft-desk__account-select[\s\S]{0,280}font-size:\s*1\.02rem/,
  "Account name uses dest-hero type, matching the platform row"
);
assert.doesNotMatch(
  selector,
  /<select/,
  "Platform picker must not open a native Windows option popup"
);
assert.doesNotMatch(
  page,
  /<select[\s\S]{0,160}id="platform-account"/,
  "Account picker must not open a native Windows option popup"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-menu[\s\S]{0,220}border-radius:\s*1[24]px/,
  "Dest option menu uses studio rounding, not a sharp OS box"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-option\.is-selected[\s\S]{0,200}background:\s*color-mix\(in srgb, #2f8f6f/,
  "Selected dest option uses mint/forest, not Windows blue"
);
assert.match(
  destSelect,
  /publish-draft-desk__dest-option-hint/,
  "Account options show the id as secondary hint, not jammed into the name"
);
assert.match(
  page,
  /hint:[\s\S]{0,80}external_account_id/,
  "Account picker still reads external_account_id from assignment authority"
);
assert.match(
  page,
  /publish-draft-desk__bay-head[\s\S]{0,1500}publish-draft-desk__heading[\s\S]{0,1200}t\("publishDraftPage\.destination"\)/,
  "Destination title is a forest heading plus status chip, not a mint pill"
);
assert.match(
  page,
  /publish-draft-desk__dest-account[\s\S]{0,180}publish-draft-desk__label[\s\S]{0,120}publishDraftPage\.destinationAccount[\s\S]{0,180}id="platform-account"/,
  "Account uses a form label beside the picker"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-eyebrow[\s\S]{0,200}font-size:\s*0\.72rem/,
  "Attempts heading still matches the Notes card eyebrow"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__bay\.is-pedestal \.publish-draft-desk__dest-sheet \.publish-draft-desk__dest-hero[\s\S]{0,200}font-size:\s*1\.02rem/,
  "Platform name writes at Caption size, not a custom masthead"
);
assert.match(
  schedule,
  /publish-draft-desk__tagbar[\s\S]{0,80}publish-draft-desk__when-stamp|publish-draft-desk__when-stamp[\s\S]{0,80}publish-draft-desk__tagbar/,
  "Date/time/timezone must reuse the hashtag tagbar well"
);
assert.match(
  page,
  /publish-draft-desk__attempts-empty/,
  "Empty attempts must still name the idle state"
);
assert.doesNotMatch(
  page,
  /publish-draft-desk__tagbar[\s\S]{0,80}publish-draft-desk__attempts-empty|publish-draft-desk__attempts-empty[\s\S]{0,80}publish-draft-desk__tagbar/,
  "Empty attempts must be a quiet sentence, not a second mint banner"
);
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__bay\.is-pedestal[\s\S]{0,220}padding:\s*10px 20px/,
  "Dest card inset must match the caption notebook, not a tighter form pad"
);
assert.match(
  caption,
  /publish-draft-desk__cta-row[\s\S]*captionEditor\.cta[\s\S]*publish-draft-desk__copy-lang[\s\S]*publishDraftPage\.language/,
  "Language stacks under CTA like dest TIME, not a trailing cell on the same row"
);
assert.match(
  caption,
  /publish-draft-desk__copy-lang[\s\S]{0,280}publish-draft-desk__lang[\s\S]{0,160}languageCode/,
  "Language vi reuses dest TIME chip chrome, not a naked notebook input"
);
assert.doesNotMatch(
  page,
  /HashtagEditor[\s\S]*publishDraftPage\.language/,
  "Language must leave the band under hashtags"
);
assert.match(
  css,
  /\.publish-draft-desk__dock\.is-pedestal \.publish-draft-desk__cta-row[\s\S]{0,200}grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  "Caption CTA uses dest account width, not a side-by-side LANGUAGE pair"
);
assert.match(
  css,
  /\.publish-draft-desk__copy-lang[\s\S]{0,180}justify-content:\s*space-between/,
  "Language sits as dest TIME header: label left, vi chip right"
);
assert.match(
  page,
  /CaptionEditor[\s\S]*HashtagEditor[\s\S]*publish-draft-desk__route[\s\S]*PublishTargetSelector[\s\S]*publish-draft-desk__account[\s\S]*mode="fields"[\s\S]*publish-draft-desk__command[\s\S]*PublishDraftGate[\s\S]*mode="actions"[\s\S]*reconcile[\s\S]*publish-draft-desk__notes[\s\S]*internalNotes/,
  "Dest fields: platform first, then account, time, verbs, then notes"
);
assert.match(
  selector,
  /visually-hidden[\s\S]{0,80}publishTargetSelector\.platform/,
  "Platform name lives in the selector; the extra Platform label must stay assistive-only"
);
assert.doesNotMatch(
  selector,
  /publish-draft-desk__dest-label[\s\S]*publishTargetSelector\.platform/,
  "Opened dest must not spend a visible Platform heading above Facebook Reels"
);
assert.match(
  page,
  /account_ref_required[\s\S]{0,220}accountRefPlaceholder/,
  "Account-ref must stay hidden unless the target requires it"
);
assert.doesNotMatch(
  page,
  /publish-draft-desk__account-ref[\s\S]{0,80}publish-draft-desk__kicker/,
  "Account-ref must not spend a pill label when it appears"
);
assert.match(
  css,
  /\.publish-draft-desk__route[\s\S]{0,180}display:\s*grid/,
  "Platform and render facts must stack, not squeeze onto one packed row"
);
assert.match(page, /publish-draft-desk__command/, "Dest verbs stay in one named region");
assert.match(
  page,
  /publish-draft-desk__dest-sheet[\s\S]*publish-draft-desk__route[\s\S]*publish-draft-desk__account[\s\S]*mode="fields"/,
  "Platform, account, and planned time must share one destination sheet"
);
assert.match(
  css,
  /\.publish-draft-desk__dest-sheet\s*\{[\s\S]{0,200}padding:\s*0/,
  "Dest sheet must not wrap fields in a nested mint card"
);
assert.match(
  gate,
  /visually-hidden[\s\S]*publishDraftPage\.scanRisk/,
  "Risk section title must stay assistive-only; chip and Run risk check already name the job"
);
assert.match(
  css,
  /\.publish-draft-desk__command \.publish-draft-desk__action\.is-schedule[\s\S]{0,180}justify-content:\s*center/,
  "Schedule must be the centered primary send action"
);
assert.match(
  css,
  /\.publish-draft-desk__command \.publish-draft-desk__action\.is-compact[\s\S]{0,160}width:\s*auto/,
  "Run risk check must stay a compact control, not a fourth full-width dump button"
);
assert.match(
  css,
  /\.publish-draft-desk__command[\s\S]{0,220}grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*1fr\)/,
  "Unschedule and Reconcile share a compact pair under the primary Schedule action"
);
assert.match(
  gate,
  /publish-draft-desk__scan-head[\s\S]*is-compact/,
  "Run risk check must sit on the risk header, not a third full-width row"
);
assert.match(
  gate,
  /publish-draft-desk__cta-row[\s\S]{0,80}publish-draft-desk__scan-head|publish-draft-desk__scan-head[\s\S]{0,80}publish-draft-desk__cta-row/,
  "Risk row must reuse the Caption CTA row: status then compact action"
);
assert.match(gate, /publishDraftPage\.scanRiskHint/, "Scan must still explain that the check does not publish");
assert.match(gate, /publishDraftPage\.scanRiskAction/, "Scan must keep a dest-specific action label");
assert.match(schedule, /type="date"/, "Planned date must be its own native date field");
assert.match(schedule, /type="time"/, "Planned time must be its own native time field");
assert.doesNotMatch(
  schedule,
  /type="datetime-local"/,
  "Dest must not use the cramped combined datetime-local popup"
);
assert.match(
  schedule,
  /joinPlannedPublishAt|splitPlannedPublishAt/,
  "Date and time fields must still write plannedPublishAt"
);
assert.match(
  schedule,
  /publish-draft-desk__when-head[\s\S]{0,80}publish-draft-desk__heading/,
  "Planned publish time uses a forest heading, not a dest eyebrow pill"
);
assert.match(
  css,
  /\.publish-draft-desk__when-stamp > label[\s\S]{0,260}border-radius:\s*999px/,
  "Date/time/timezone cells must use hashtag pill geometry, not a spreadsheet"
);
assert.match(
  css,
  /\.publish-draft-desk__when-stamp\s*\{[\s\S]{0,320}border-radius:\s*1[24]px/,
  "Date/time/timezone must share one stamp well, not three loose boxes"
);
assert.match(
  schedule,
  /publish-draft-desk__when-icon|function WhenStampIcon/,
  "Stamp cells must own calendar/clock/zone icons, not native chrome alone"
);
assert.match(
  schedule,
  /publish-draft-desk__chip[\s\S]{0,180}publish-draft-desk__when-status|publish-draft-desk__when-status[\s\S]{0,180}publish-draft-desk__chip/,
  "Unscheduled/Scheduled must use the dest chip, not a leftover grey pill"
);
assert.match(
  schedule,
  /aria-label=\{scheduleStatus\}/,
  "Chip stays short; full scheduled datetime remains assistive"
);
assert.match(
  schedule,
  /visually-hidden[\s\S]*publishSchedulePanel\.date/,
  "Date/time/timezone kickers must stay assistive-only under Planned publish time"
);
assert.doesNotMatch(
  schedule,
  /publish-draft-desk__when-kicker/,
  "Stamp fields must not spend a visible Date/Time/Timezone row"
);
assert.match(
  css,
  /\.publish-draft-desk__command \.publish-draft-desk__action\.is-schedule:disabled[\s\S]{0,200}opacity:\s*1/,
  "Idle Schedule must stay a forest control, not a washed-out grey bar"
);
assert.match(
  css,
  /\.publish-draft-desk__scan\s*\{[\s\S]{0,220}border-top:\s*1px solid/,
  "Risk check must split with a notebook hairline, not sit in a floating mint box"
);
assert.match(
  gate,
  /leadingIcon[\s\S]*ScanIcon|kind="scan"/,
  "Scan must keep an icon like the other dest verbs"
);
assert.doesNotMatch(
  gate,
  /riskSummary\.runRiskScan/,
  "Dest Scan must not reuse the opaque Final Review Scan label"
);
assert.match(
  css,
  /\.publish-draft-desk__command \.publish-draft-desk__action[\s\S]{0,280}min-height:\s*36px/,
  "Dest verbs must stay compact studio cards"
);
assert.doesNotMatch(
  page,
  /publishesApprovedRender/,
  "Dest must not spend a row on the always-visible publish hint"
);
assert.match(
  schedule,
  /publish-draft-desk__when-status/,
  "Unscheduled must sit on the time field, not a separate pill row"
);
assert.match(
  schedule,
  /mode === "fields"|mode === "actions"/,
  "Schedule panel must split time/tz fields from Schedule/Unschedule verbs"
);
{
  const notesStart = page.indexOf('className="publish-draft-desk__notes"');
  const notesBlock = page.slice(notesStart, notesStart + 2200);
  assert.match(
    notesBlock,
    /internalNotes[\s\S]*publish-draft-desk__note-pair[\s\S]*platformNotes[\s\S]*schedulingNotes/,
    "Open notes must keep internal then platform | scheduling"
  );
  assert.doesNotMatch(notesBlock, /languageCode|platformAccountRef/, "Language and account-ref must leave the notes dump");
}
assert.match(
  css,
  /\.publish-draft-desk\.is-stage \.publish-draft-desk__notes[\s\S]{0,280}inset 4px 0 0 #2a4d41/,
  "Notes must always use the Operator Studio forest spine, not only when opened"
);
assert.doesNotMatch(css, /\.publish-draft-desk__notes\[open\]/, "Notes CSS must not depend on a closed details state");
assert.match(page, /publishDraftPage\.notesOptional/, "Notes still name themselves as optional");
assert.ok(en.publishDraftHeader.titleField || en.publishDraftPage.destination, "en must name title or destination");
assert.ok(vi.publishDraftHeader.titleField || vi.publishDraftPage.destination, "vi must name title or destination");
assert.match(en.publishDraftPage.scanRiskHint, /does not publish/i, "Scan copy must say the action does not publish");
assert.match(vi.publishDraftPage.scanRiskHint, /không đăng/i, "Vietnamese Scan copy must say the action does not publish");
assert.ok(en.publishDraftPage.scanRiskAction, "Scan action must have a dest-specific label");
assert.ok(vi.publishDraftPage.scanRiskAction, "Vietnamese Scan action must have a dest-specific label");

console.log("publish-draft detail desk tests passed");
