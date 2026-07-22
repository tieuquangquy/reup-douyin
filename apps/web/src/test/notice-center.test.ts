import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { upsertNotice, type AppNotice } from "../components/shared/NoticeCenter";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const rootLayoutSource = readFileSync(resolve(webRoot, "app/layout.tsx"), "utf8");
const appShellSource = readFileSync(resolve(webRoot, "components/app-shell/AppShell.tsx"), "utf8");
const noticeSource = readFileSync(resolve(webRoot, "components/shared/NoticeCenter.tsx"), "utf8");
const globalCssSource = readFileSync(resolve(webRoot, "app/globals.css"), "utf8");

const first: AppNotice = { id: "save", message: "Saved", tone: "success", createdAt: 1 };
const replacement: AppNotice = { id: "save", message: "Saved again", tone: "success", createdAt: 2 };
const deduped = upsertNotice([first], replacement);
assert.equal(deduped.length, 1, "Notices with the same ID must be deduplicated");
assert.equal(deduped[0]?.message, "Saved again", "Newest duplicate notice must replace stale copy");

assert.match(rootLayoutSource, /<NoticeProvider>[\s\S]*<AuthProvider>/, "Root layout must preserve notices across authenticated page navigation");
assert.match(appShellSource, /<NoticeViewport \/>/, "Authenticated AppShell must own the visible toast viewport");
assert.match(noticeSource, /role=\{notice\.tone === "error" \? "alert" : "status"\}/, "Errors must alert while success and info announce politely");
assert.match(noticeSource, /message: string/, "Global notices must accept plain text rather than raw HTML");
assert.match(noticeSource, /DEFAULT_NOTICE_DURATION_MS/, "Success and info notices must have a standard expiry");
assert.match(noticeSource, /export function InlineNotice/, "Important progress and errors must have a reusable inline convention");
assert.match(noticeSource, /className=\{`app-inline-notice is-\$\{tone\}`\}/, "Inline notices must share semantic tone styling");
assert.doesNotMatch(noticeSource, /querySelector<HTMLElement>\("\.app-topbar"\)/, "Bottom toast placement must not depend on topbar measurement");
assert.match(globalCssSource, /\.app-notice-viewport\s*\{[^}]*position: fixed;/, "Notice viewport must remain visible while a long page scrolls");
assert.match(
  globalCssSource,
  /\.app-notice-viewport\s*\{[^}]*bottom: max\(76px, calc\(env\(safe-area-inset-bottom\) \+ 68px\)\);/,
  "Desktop toasts must sit above the Back to top control and safe area"
);
assert.match(
  globalCssSource,
  /@media \(max-width: 640px\)[\s\S]*?\.app-notice-viewport\s*\{[^}]*bottom: max\(68px, calc\(env\(safe-area-inset-bottom\) \+ 62px\)\);/,
  "Mobile toasts must remain centered above the compact Back to top control"
);

console.log("notice center tests passed");
