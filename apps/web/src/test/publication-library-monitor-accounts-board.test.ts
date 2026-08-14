/** Monitor board — one polished stage: donut + lane bars + ops stats. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/PublicationTrackingMonitor.tsx"), "utf8");
const cssAll = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");

const marker = "/* Publication Library Monitor v80";
const start = cssAll.indexOf(marker);
assert.ok(start >= 0, "Monitor v80 CSS block must exist");
const css = cssAll.slice(start, start + 80_000);

assert.match(page, /tracking-monitor-page is-v80/, "Monitor must use the Accounts-board composition");
assert.doesNotMatch(page, /tracking-monitor-pulse/, "Monitor must not keep the v72 pulse line as the KPI surface");
assert.match(page, /spectrum__stage/, "Spectrum must use one polished stage card");
assert.match(
  page,
  /spectrum__stage[\s\S]{0,400}?spectrum__head[\s\S]{0,800}?spectrum__donut[\s\S]{0,800}?spectrum__bars[\s\S]{0,2000}?spectrum__metrics/,
  "Title, donut, bars, and one even metric grid must live in one full-width stage",
);
assert.match(
  page,
  /spectrum__metrics[\s\S]{0,800}?trackedViews[\s\S]{0,400}?active_count[\s\S]{0,400}?nextDue[\s\S]{0,400}?due_soon_count[\s\S]{0,400}?snapshots_today_count[\s\S]{0,400}?growingCount[\s\S]{0,400}?needs_attention_count[\s\S]{0,400}?lastMeasured/,
  "Metric grid must keep views, active, cadence, snapshots, growing, attention, and last measured",
);
assert.match(
  page,
  /function compactDateTime\(/,
  "Long datetimes must be shortened so metric tiles stay even",
);
assert.doesNotMatch(
  page,
  /spectrum__ops|spectrum__info/,
  "Ops and info must merge into one metric grid instead of two cramped 2x2 clusters",
);
assert.match(
  page,
  /barW[\s\S]{0,180}?length === 0 \? 0/,
  "Empty lanes must set bar width to 0, not a 10% stub",
);
assert.match(
  page,
  /spectrum__metrics[\s\S]{0,500}?is-views[\s\S]{0,300}?is-active[\s\S]{0,300}?is-next[\s\S]{0,300}?is-due/,
  "Metric tiles must keep distinct kinds for views, active, next due, and due soon",
);
assert.match(
  page,
  /conic-gradient[\s\S]{0,400}?attentionDeg[\s\S]{0,200}?dueDeg[\s\S]{0,200}?steadyDeg/,
  "Donut slices must be computed from Attention, Due, Steady, and Parked counts",
);
assert.doesNotMatch(
  page,
  /spectrum__table[\s\S]{0,800}?monitorLanes\.map|spectrum__cell is-lane/,
  "Lane counts must live on the bars, not a duplicate 8-cell table",
);
assert.doesNotMatch(
  page,
  /donut-core[\s\S]{0,200}?trackingMonitor\.schedules/,
  "Donut core must show the count only so the label is not truncated",
);
assert.doesNotMatch(
  page,
  /laneMixHint|pulseTitle|pulseHint|activeHint|snapshotsTodayHint|growingHint|"laneMix"|t\("trackingMonitor\.laneMix"\)/,
  "Polished stage must drop panel titles and per-metric hint copy",
);
assert.doesNotMatch(
  page,
  /spectrum__legend|spectrum__chart-body|spectrum__poster|spectrum__pulse|spectrum__kpis|spectrum__main|spectrum__table/,
  "Polished stage must not revive the old card-deck or 8-cell table",
);
assert.doesNotMatch(
  page,
  /spectrum__facts|spectrum__groups|spectrum__pills|spectrum__waffle|spectrum__fan|spectrum__ribbon|spectrum__plot|spectrum__rows|scheduleLabel|--seg-w|--spoke-|--col-h|--row-w/,
  "Board must drop superseded chart skins",
);
assert.doesNotMatch(
  page,
  /is-chart-deck|is-dense|spectrum__gauges|spectrum__hero|spectrum__mix|spectrum__col|spectrum__cadence-axis|spectrum__beads/,
  "Chart band must not revive unlabeled beads, empty time axes, mix tracks, or mixed gauges",
);
assert.match(page, /function monitorLane\([\s\S]{0,900}?return "parked"/, "Schedules must triage into Attention, Due, Steady, or Parked");
assert.match(
  page,
  /spectrum__bars[\s\S]{0,900}?setLaneFilter[\s\S]{0,200}?lane\.key/,
  "Lane bars must remain clickable filters for the roster",
);
assert.match(
  page,
  /tracking-monitor-table__group[\s\S]{0,500}?aria-expanded[\s\S]{0,400}?title=\{lane\.hint\}/,
  "Lane group headers must keep the hint as title, not inline copy",
);
assert.doesNotMatch(
  page,
  /table__group[\s\S]{0,500}?<small>\{lane\.hint\}<\/small>/,
  "Lane group headers must not repeat spectrum lane copy inline",
);
assert.match(
  page,
  /QUIET_HEALTH_REASONS[\s\S]{0,200}?tracking_healthy[\s\S]{0,120}?tracking_window_completed/,
  "Quiet health reasons must include healthy and completed echoes",
);
assert.match(
  page,
  /function rowHealthNote\([\s\S]{0,220}?QUIET_HEALTH_REASONS\.has/,
  "Health column must hide quiet reasons that only echo the badge",
);
assert.match(
  page,
  /const healthNote = rowHealthNote\(item\)[\s\S]{0,2500}?table__state/,
  "Health secondary line must come from rowHealthNote, not always-on health_reason",
);
assert.match(
  page,
  /const parked = isParked\(item\)[\s\S]{0,300}?next_collection_at[\s\S]{0,200}?last_completed_at[\s\S]{0,200}?windowPrimary = parked/,
  "Parked NEXT must prefer last measured; active NEXT must prefer next collection",
);
assert.match(
  page,
  /table__window\$\{parked \? " is-parked" : ""\}/,
  "NEXT cell must mark parked rows for the quieter cadence treatment",
);
assert.match(
  page,
  /table__performance\$\{[\s\S]{0,180}?GROWING[\s\S]{0,120}?is-growing/,
  "Views cell must mark GROWING rows for the positive tint",
);
assert.match(
  page,
  /thumbnail_url \?[\s\S]{0,160}?<span aria-hidden="true" \/>|<span aria-hidden="true"><\/span>/,
  "Missing reel thumbs must use a quiet placeholder, not the word Reel",
);
assert.match(
  page,
  /function workloadNote\([\s\S]{0,500}?COMPLETED/,
  "Snapshots column must hide quiet COMPLETED job noise and keep actionable job notes only",
);
assert.match(
  page,
  /table__window[\s\S]{0,500}?compactDateTime|windowPrimary[\s\S]{0,200}?compactDateTime/,
  "Roster NEXT column must use compact datetimes instead of long wall-clock strings",
);
assert.doesNotMatch(
  page,
  /board__head[\s\S]{0,400}?tableViewHint/,
  "Board header must not repeat the triage hint under the title",
);
assert.doesNotMatch(
  page,
  /tracking-monitor-table__meta/,
  "Roster must not repeat the spectrum total and table hint above the table",
);
assert.match(
  page,
  /tracking-monitor-table__action[\s\S]{0,400}?pauseTracking[\s\S]{0,500}?resumeTracking/,
  "Pause and Resume must remain row actions",
);
assert.match(page, /tracking-monitor-drawer/, "Schedule and snapshot details must stay in the drawer");
assert.doesNotMatch(page, /tracking-monitor-grid|tracking-monitor-tile|tracking-monitor-scoreboard/, "Monitor must not revive tile or scoreboard layouts");
assert.match(page, /fetchPublicationMetricTrackingMonitor/, "Monitor must keep the aggregated monitor endpoint as authority");

assert.match(
  css,
  /tracking-monitor-spectrum\.is-metric-band \{[\s\S]{0,280}?background:\s*#f4f8f6/,
  "Spectrum must read as one quiet mint band like Insights metrics",
);
assert.match(
  css,
  /spectrum__stage \{[\s\S]{0,900}?width:\s*100%/,
  "Stage card must span the mint band",
);
assert.match(
  css,
  /spectrum__stage \{[\s\S]{0,900}?grid-template-columns:\s*auto\s+minmax\(0,\s*1/,
  "Lane bars must take the flexible middle column so the band fills evenly",
);
assert.match(
  css,
  /spectrum__metrics \{[\s\S]{0,220}?grid-template-columns:\s*repeat\(4/,
  "Metric tiles must sit in one even 4-column grid",
);
assert.doesNotMatch(
  css,
  /spectrum__stage \{[\s\S]{0,900}?width:\s*max-content/,
  "Stage must not hug left and leave a hollow mint void",
);
assert.doesNotMatch(
  css,
  /spectrum__bars > button\.is-empty \{[\s\S]{0,80}?opacity:\s*0\.[0-5]/,
  "Empty lane rows must stay readable instead of fading to ~40% opacity",
);
assert.doesNotMatch(
  css,
  /spectrum__metrics > div\.is-empty \{[\s\S]{0,80}?opacity:\s*0\.[0-6]/,
  "Empty metric tiles must keep readable contrast",
);
assert.match(
  css,
  /spectrum__donut \{[\s\S]{0,420}?width:\s*[56]\./,
  "Donut must be large enough to hold the count without truncation",
);
assert.match(
  css,
  /spectrum__bars[\s\S]{0,500}?--bar-w/,
  "Lane bars must size from --bar-w",
);
assert.match(
  css,
  /spectrum__metrics > div \{[\s\S]{0,280}?background:/,
  "Metric tiles must sit on tinted surfaces",
);
assert.match(
  css,
  /spectrum__metrics > div \{[\s\S]{0,280}?border:/,
  "Metric tiles must share one quiet edge instead of stacked rails",
);
assert.match(
  css,
  /spectrum__metrics > div \{[\s\S]{0,280}?border-radius:\s*1[12]px/,
  "Metric tiles must stay round instead of hard 8px cards",
);
assert.match(
  css,
  /spectrum__metrics > div\.is-views \{[\s\S]{0,140}?background:/,
  "Kind tiles must use a whisper fill, not only a hard left rail",
);
assert.doesNotMatch(
  css,
  /spectrum__metrics[\s\S]{0,2800}?box-shadow:\s*inset 3px/,
  "Metric tiles must drop the heavy 3px inset rail",
);
assert.match(
  css,
  /spectrum__bars > button\.is-attention \{[\s\S]{0,160}?background:|bars > button\.is-attention[\s\S]{0,80}?background:/,
  "Lane rows must carry a tint so the chart is not a flat white strip",
);
assert.doesNotMatch(
  css,
  /tracking-monitor-table__meta \{/,
  "v80 CSS must not keep the leftover roster meta strip",
);
assert.match(
  css,
  /tracking-monitor-table tbody\.is-steady \{[\s\S]{0,160}?--lane-soft:\s*var\(--tm-steady-soft\)|--lane-soft:\s*#e7f5ef/,
  "Steady lane band must stay mint but readable against white rows",
);
assert.match(
  css,
  /tracking-monitor-table tbody\.is-parked \{[\s\S]{0,160}?--lane-soft:\s*var\(--tm-parked-soft\)|--lane-soft:\s*#eef2f0/,
  "Parked lane band must stay distinct from Steady",
);
assert.match(
  css,
  /tracking-monitor-table__group th \{[\s\S]{0,320}?border-left:/,
  "Lane group headers must read as a soft lane rail, not a flat slab",
);
assert.match(
  css,
  /col\.is-reel \{[\s\S]{0,80}?width:\s*3[2-8]%/,
  "REEL column must claim the scan column so other cells stop floating in whitespace",
);
assert.match(
  css,
  /col\.is-state \{[\s\S]{0,80}?width:\s*1[2-5]%/,
  "HEALTH column must stay compact instead of an 18% hollow lane",
);
assert.match(
  css,
  /col\.is-window \{[\s\S]{0,80}?width:\s*1[2-5]%/,
  "NEXT column must stay compact so cadence chips do not stretch",
);
assert.match(
  css,
  /\.tracking-monitor-page\.is-v80 \{[\s\S]{0,500}?--tracking-monitor-axis:\s*0\.6875rem[\s\S]{0,200}?--tracking-monitor-data:\s*0\.875rem[\s\S]{0,200}?--tracking-monitor-kpi:\s*1rem/,
  "v80 must publish one page type scale: axis 11, data 14, kpi 16",
);
assert.match(
  css,
  /\.tracking-monitor-page\.is-v80 \{[\s\S]{0,900}?--tm-label-quiet:\s*#6b8278[\s\S]{0,120}?--tm-label-strong:\s*#2a4d41/,
  "v80 must publish quiet/strong label colors for headers and titles",
);
assert.match(
  css,
  /\.tracking-monitor-page\.is-v80 \{[\s\S]{0,1200}?--tm-steady:\s*#2f8f6f[\s\S]{0,200}?--tm-due:\s*#3a7eb0[\s\S]{0,200}?--tm-attention:\s*#c4841a[\s\S]{0,200}?--tm-parked:\s*#6f857c/,
  "v80 must publish semantic lane label colors Steady/Due/Attention/Parked",
);
assert.match(
  css,
  /spectrum__metrics > div > span \{[\s\S]{0,160}?color:\s*var\(--tm-label-quiet\)/,
  "Spectrum metric labels must use the quiet label token",
);
assert.match(
  css,
  /tracking-monitor-table thead th \{[\s\S]{0,220}?color:\s*var\(--tm-label-quiet\)/,
  "Column headers must use the quiet label token",
);
assert.match(
  css,
  /tracking-monitor-reel > img[\s\S]{0,400}?height:\s*4[2-8]px/,
  "Reel thumbs must be large enough to scan as media, not tiny chips",
);
assert.match(
  css,
  /table__performance > span \{[\s\S]{0,220}?height:\s*[6-9]px/,
  "Views engagement bar must be thick enough to read at a glance",
);
assert.match(
  css,
  /table__performance > span \{[\s\S]{0,220}?background:\s*#(d[0-9a-f]{5}|c[0-9a-f]{5})/i,
  "Views bar track must contrast against the white row",
);
assert.match(
  css,
  /table__performance\.is-growing small|performance\.is-growing[\s\S]{0,120}?color:/,
  "Growing trend copy must carry a positive tint for scanability",
);
assert.match(
  css,
  /tracking-monitor-table__group th \{[\s\S]{0,320}?border-radius:/,
  "Lane group headers must soften instead of hard full-bleed bars",
);
assert.doesNotMatch(
  css,
  /tracking-monitor-spectrum__main \{|tracking-monitor-spectrum__chart-body \{|tracking-monitor-spectrum__poster \{|tracking-monitor-spectrum__pulse \{|tracking-monitor-spectrum__kpis \{|tracking-monitor-spectrum__table \{|tracking-monitor-spectrum__viz \{/,
  "v80 CSS must not keep the stacked table + hollow viz layout",
);
assert.doesNotMatch(
  css,
  /"poster body pulse"/,
  "Spectrum must not revive the old three-area grid that left hollow stretch",
);
assert.doesNotMatch(
  css,
  /spectrum__facts \{|spectrum__groups \{|spectrum__pills \{|spectrum__waffle \{|spectrum__fan \{|spectrum__ribbon \{|spectrum__plot \{|spectrum__rows \{|spectrum__mix \{|spectrum__col \{|spectrum__cadence-axis \{|spectrum__beads \{/,
  "v80 CSS must not keep superseded chart skins",
);

assert.match(en, /"trackedViews"/, "en.json must keep tracked-views label");
assert.match(vi, /"trackedViews"/, "vi.json must keep tracked-views label");
assert.match(en, /"nextDue"/, "en.json must keep next-due label");
assert.match(vi, /"nextDue"/, "vi.json must keep next-due label");
assert.match(en, /"lastMeasured"/, "en.json must keep last-measured label");
assert.match(vi, /"lastMeasured"/, "vi.json must keep last-measured label");

console.log("publication-library-monitor-accounts-board: PASS");
