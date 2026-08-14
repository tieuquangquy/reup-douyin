/** Tracking Monitor detail drawer v81: caption/page-first header, dense metrics, merged schedule+job, timeline, sticky footer. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationTrackingMonitor.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

const v81Start = cssFull.indexOf("/* Tracking Monitor Drawer v81");
assert.ok(v81Start >= 0, "v81 tracking drawer polish CSS block must exist");
const v81 = cssFull.slice(v81Start, v81Start + 12000);

assert.match(page, /tracking-monitor-page is-v80 is-v81/, "Monitor page must opt into drawer v81");
assert.match(page, /tracking-monitor-drawer is-v81/, "Detail drawer must mark is-v81");
assert.match(page, /tracking-monitor-drawer__identity/, "Drawer header must use identity composition");
assert.match(page, /thumbnail_url[\s\S]{0,120}?tracking-monitor-drawer__thumb|tracking-monitor-drawer__thumb[\s\S]{0,80}?thumbnail_url/, "Drawer identity must surface thumbnail when present");
assert.match(page, /drawerTitle|page_display_name[\s\S]{0,200}?external_reel_id/, "Title must prefer human caption/page over raw reel id as hero");
assert.doesNotMatch(
  page,
  /<strong>\{selected\.caption \|\| selected\.external_reel_id \|\| "Reel"\}<\/strong>/,
  "Hero title must not fall straight through to external_reel_id UUID",
);
assert.match(page, /tracking-monitor-drawer__body/, "Drawer must scroll body separately from sticky footer");
assert.match(page, /tracking-monitor-drawer__panel/, "Schedule and latest job must share one facts panel");
assert.match(page, /tracking-monitor-drawer__metrics|tracking-monitor-drawer-metrics is-v81/, "Metrics strip must opt into v81 density");
assert.match(page, /tracking-monitor-drawer__footer|tracking-monitor-drawer > footer/, "Actions must stay in sticky footer");
assert.match(
  page,
  /tracking-monitor-drawer__footer[\s\S]{0,500}?leadingIcon=\{<MonitorIcon kind="publication"/,
  "Open publication must show a publication glyph",
);
assert.match(
  page,
  /external_permalink[\s\S]{0,220}?MonitorIcon kind="external"/,
  "Open on Facebook must show an external-link glyph",
);
assert.match(
  page,
  /tracking-monitor-drawer__footer[\s\S]{0,900}?leadingIcon=\{<MonitorIcon kind="pause"/,
  "Pause action in drawer footer must reuse the pause glyph",
);
assert.match(
  page,
  /tracking-monitor-drawer__footer[\s\S]{0,1200}?leadingIcon=\{<MonitorIcon kind="play"/,
  "Resume action in drawer footer must reuse the play glyph",
);

assert.match(v81, /--pl-iq-mint|--tm-label-quiet|--tm-label-strong/, "v81 CSS must use Intelligence / monitor label tokens");
assert.match(v81, /--tm-drawer-eyebrow|--tm-drawer-meta|--tm-drawer-body|--tm-drawer-title|--tm-drawer-score|--tm-drawer-btn/, "v81 must define drawer type-scale vars");
assert.match(v81, /\.tracking-monitor-drawer\.is-v81/, "v81 CSS must scope to the drawer mark");
assert.match(v81, /tracking-monitor-drawer__identity/, "v81 must style identity header");
assert.match(v81, /tracking-monitor-drawer__panel/, "v81 must style merged schedule/job panel");
assert.match(v81, /position:\s*sticky/, "v81 footer must remain sticky");

console.log("tracking-monitor-drawer-polish: PASS");
