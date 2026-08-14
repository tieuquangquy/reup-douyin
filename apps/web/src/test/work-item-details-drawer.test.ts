/**
 * Work Item Details must open as an Ops-Users-style right drawer overlay
 * (not a sticky side column) on Capture / Review / Reup.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const drawerSource = readFileSync(resolve(webSrc, "components/shared/WorkItemDetailsDrawer.tsx"), "utf8");
const captureSource = readFileSync(resolve(webSrc, "components/capture-inbox/CaptureInboxPage.tsx"), "utf8");
const reviewSource = readFileSync(resolve(webSrc, "components/review-board/ReviewBoardPage.tsx"), "utf8");
const reupSource = readFileSync(resolve(webSrc, "components/reup-queue/ReupQueuePage.tsx"), "utf8");
const cssSource = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

assert.match(drawerSource, /export function WorkItemDetailsDrawer/, "Shared WorkItemDetailsDrawer must exist");
assert.match(drawerSource, /role="dialog"/, "Drawer must expose dialog role");
assert.match(drawerSource, /aria-modal="true"/, "Drawer must be modal");
assert.match(drawerSource, /work-item-details-drawer-backdrop/, "Drawer must use dedicated backdrop class");
assert.match(drawerSource, /work-item-details-drawer/, "Drawer must use dedicated panel class");
assert.match(drawerSource, /if \(!open\) return null/, "Drawer must not render when closed");
assert.match(drawerSource, /onClick=\{onClose\}/, "Backdrop must close the drawer");
assert.match(drawerSource, /stopPropagation/, "Panel click must not close the drawer");
assert.match(drawerSource, /headerExtra\?:/, "Drawer must accept optional headerExtra under the title");
assert.match(drawerSource, /work-item-details-drawer-header__extra/, "Drawer must render headerExtra in a dedicated header slot");
assert.match(drawerSource, /headerLeading\?:/, "Drawer must accept optional headerLeading before the title");
assert.match(drawerSource, /work-item-details-drawer-header__leading/, "Drawer must render headerLeading in a dedicated header slot");

assert.match(captureSource, /WorkItemDetailsDrawer/, "Capture Inbox must use WorkItemDetailsDrawer");
assert.doesNotMatch(captureSource, /capture-inbox-review-side/, "Capture Inbox must not reserve sticky side column");
assert.match(captureSource, /openItemDetails/, "Capture must keep details opener");

assert.match(reviewSource, /WorkItemDetailsDrawer/, "Review Board must use WorkItemDetailsDrawer");
assert.doesNotMatch(reviewSource, /capture-inbox-review-side/, "Review Board must not reserve sticky side column");

assert.match(reupSource, /WorkItemDetailsDrawer/, "Reup Queue must use WorkItemDetailsDrawer");
assert.doesNotMatch(reupSource, /capture-inbox-review-side/, "Reup Queue must not reserve sticky side column");

assert.match(
  cssSource,
  /\.capture-inbox-review-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/,
  "Work workspace must be single-column full width"
);
assert.match(cssSource, /\.work-item-details-drawer-backdrop/, "CSS must style drawer backdrop");
assert.match(cssSource, /\.work-item-details-drawer\s*\{/, "CSS must style drawer panel");
assert.match(cssSource, /\.work-item-details-drawer__body/, "CSS must style drawer scroll body");

console.log("work-item-details-drawer tests passed");
