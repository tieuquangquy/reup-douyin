import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = join(testDir, "..");
const repoRoot = join(testDir, "..", "..", "..", "..");

const pageSource = readFileSync(join(webRoot, "components/ops-console/OpsUsersPage.tsx"), "utf8");
const routeSource = readFileSync(join(webRoot, "app/ops/users/page.tsx"), "utf8");
const navSource = readFileSync(join(webRoot, "lib/navigationConfig.ts"), "utf8");
const apiSource = readFileSync(join(webRoot, "lib/api.ts"), "utf8");
const enSource = readFileSync(join(webRoot, "lib/i18n/en.json"), "utf8");
const globalCssSource = readFileSync(join(webRoot, "app/globals.css"), "utf8");

assert.match(routeSource, /OpsUsersPage/, "Ops users route must render OpsUsersPage");
assert.match(navSource, /href: "\/ops\/users"/, "Ops nav must include Users");
assert.match(navSource, /opsNavSections[\s\S]*label: "nav\.users"/, "Users must live on Ops sidebar");
assert.doesNotMatch(
  navSource.slice(0, navSource.indexOf("export const opsNavSections")),
  /label: "nav\.users"/,
  "Users must not appear in Operator Studio nav"
);
assert.match(apiSource, /\/auth\/workspace\/members/, "Web API must call workspace members endpoint");
assert.match(apiSource, /createWorkspaceInvite/, "Web API must support invite create");
assert.match(apiSource, /updateWorkspaceMember/, "Web API must support member update");
assert.match(apiSource, /resetWorkspaceMemberPassword/, "Web API must support password reset");
assert.match(apiSource, /rotateWorkspaceInvite/, "Web API must support invite rotate");
assert.match(apiSource, /display_name/, "Web API member patch must support display_name");
assert.match(apiSource, /phone/, "Web API member patch must support phone");
assert.match(apiSource, /address/, "Web API member patch must support address");
assert.match(apiSource, /notes/, "Web API member patch must support notes");
assert.match(apiSource, /lastSeenAt|last_seen_at/, "Web API members must expose last seen");

assert.match(pageSource, /OpsConsoleShell/, "Users page must own Ops shell so refresh can live in the topbar");
assert.match(pageSource, /TopbarRefreshButton/, "Users page must use icon refresh in the topbar");
assert.doesNotMatch(pageSource, /OpsPageHeader/, "Users page must not duplicate shell title with OpsPageHeader");
assert.match(pageSource, /ops-users-sheet/, "Users page must use a polished sheet surface around the roster");
assert.match(pageSource, /ops-users-chrome/, "Filters and invite must live in compact chrome");
assert.match(pageSource, /ops-users-table/, "Members must use a table skeleton");
assert.match(pageSource, /<table[\s\S]*ops-users-table/, "Members roster must be a real HTML table");
assert.match(pageSource, /ops-users-toolbar/, "Members toolbar must host search");
assert.doesNotMatch(pageSource, /ops-users-gallery/, "Gallery card deck must be retired");
assert.doesNotMatch(pageSource, /ops-users-deck/, "Card deck grid must be retired");
assert.doesNotMatch(pageSource, /ops-users-card/, "Gallery cards must be retired");
assert.doesNotMatch(pageSource, /ops-users-atelier/, "Atelier split-pane shell must stay retired");
assert.doesNotMatch(pageSource, /ops-users-band/, "Dark band header must stay retired");
assert.doesNotMatch(pageSource, /ops-users-split/, "Split ledger + inspect layout must stay retired");
assert.doesNotMatch(pageSource, /ops-users-ledger/, "Left ledger pane must stay retired");
assert.doesNotMatch(pageSource, /ops-users-inspect/, "Sparse inspect panel must stay retired");
assert.doesNotMatch(pageSource, /ops-users-masthead/, "Marketing masthead layout must stay retired");
assert.doesNotMatch(pageSource, /ops-users-seg/, "Segmented pill strip must stay retired");
assert.doesNotMatch(pageSource, /ops-users-directory/, "Single-column directory card must stay retired");
assert.doesNotMatch(pageSource, /ops-users-person/, "Sparse person rows must stay retired");
assert.doesNotMatch(pageSource, /ops-users-metrics/, "Large metric card strip must stay removed");
assert.doesNotMatch(pageSource, /ops-users-rail/, "Left filter rail must stay removed");
assert.match(
  globalCssSource,
  /\.ops-users-sheet-page\s+\.ops-users-table\s*\{[^}]*table-layout:\s*fixed/,
  "Users roster must use table-layout:fixed so columns distribute evenly"
);
assert.match(
  globalCssSource,
  /\.ops-users-sheet-page\s+\.ops-users-table\s+th:nth-child\(2\)[\s\S]*?width:\s*15%/,
  "Role/Status/date columns must share even widths (not shrink-wrap 1%)"
);
assert.match(
  globalCssSource,
  /\.ops-users-sheet-page\s+\.ops-users-table\s+th:nth-child\(6\)[\s\S]*?width:\s*12%/,
  "Actions column must keep a real share of the row width"
);
assert.match(
  globalCssSource,
  /\.ops-users-table\s+\.ops-users-member-row\s*\{[^}]*display:\s*table-row/,
  "Table rows must remain display:table-row (never grid on tr)"
);
assert.match(pageSource, /ops-users-drawer/, "Edit member must use a side drawer");
assert.match(pageSource, /ops-users-drawer__body/, "Edit drawer must scroll body separately from chrome");
assert.match(pageSource, /ops-users-drawer__footer/, "Edit drawer must pin Cancel/Save in a sticky footer");
assert.match(pageSource, /ops-users-switch/, "Access control must use a custom switch, not a bare checkbox");
assert.match(pageSource, /ops-users-email-readonly/, "Email must render as read-only identity text, not a disabled input");
assert.match(globalCssSource, /\.ops-users-drawer__body/, "CSS must style scrollable drawer body");
assert.match(globalCssSource, /\.ops-users-drawer__footer/, "CSS must style sticky drawer footer");
assert.match(globalCssSource, /\.ops-users-switch/, "CSS must style accent access switch");
assert.match(pageSource, /ops-users-modal/, "Invite must use a modal dialog");
assert.match(pageSource, /ops-users-canvas/, "Users page must use a distinctive canvas surface");
assert.match(pageSource, /ops-users-role-chip/, "Roles must use distinctive role chips");
assert.match(pageSource, /opsUsers\.inviteMember|opsUsers\.addMember/, "Primary add CTA must be Invite member");
assert.match(pageSource, /opsUsers\.editMember|opsUsers\.edit/, "Row must expose Edit action");
assert.match(
  pageSource,
  /filteredMembers\.map[\s\S]*ops-tts-setup-switch[\s\S]*member\.isActive/,
  "Members Status column must use an on/off switch bound to isActive"
);
assert.match(
  pageSource,
  /aria-label=\{t\("opsUsers\.editMember"\)\}/,
  "Edit must be an icon button with aria-label (not text CTA)"
);
assert.match(
  pageSource,
  /ops-tts-setup-table__icon-btn|ops-users-icon-btn/,
  "Edit must use an icon button chrome"
);
assert.doesNotMatch(
  pageSource,
  /filteredMembers\.map[\s\S]*?\{t\("opsUsers\.enable"\)\}/,
  "Members Actions must not show Enable text button"
);
assert.doesNotMatch(
  pageSource,
  /filteredMembers\.map[\s\S]*?\{t\("opsUsers\.disable"\)\}/,
  "Members Actions must not show Disable text button"
);
assert.match(pageSource, /editDisplayName|displayName/, "Edit drawer must support display name");
assert.match(pageSource, /editPhone|phone/, "Edit drawer must support phone");
assert.match(pageSource, /editAddress|address/, "Edit drawer must support address");
assert.match(pageSource, /editNotes|notes/, "Edit drawer must support notes");
assert.match(pageSource, /editActive|accessActive/, "Edit drawer must support access toggle");
assert.match(pageSource, /roleHints/, "Edit drawer must explain role implications");
assert.match(pageSource, /resetWorkspaceMemberPassword|resetPassword/, "Edit drawer must support password reset");
assert.match(pageSource, /rotateWorkspaceInvite|copyNewLink/, "Pending invites must offer copy-new-link rotate");
assert.match(pageSource, /lastActive|lastSeenAt/, "Members list must show last active");
assert.match(pageSource, /accessFilter|filterAccess|applyMetric/, "Members list must support access views");
assert.match(pageSource, /window\.confirm|ops-users-confirm/, "Disable/Remove/reset must confirm before applying");
assert.match(pageSource, /searchQuery|setSearchQuery/, "Members list must support search");
assert.match(pageSource, /roleFilter|setRoleFilter/, "Members list must support role filter");
assert.match(pageSource, /ops-users-pending/, "Pending invites must render in the pending view");
assert.doesNotMatch(pageSource, /ops-users-aside/, "Invite form must not permanently occupy a left column");
assert.match(pageSource, /\/auth\/invite\?token=/, "Users page must build invite accept link");

assert.match(enSource, /"inviteMember"/, "English i18n must include Invite member CTA");
assert.match(enSource, /"editMember"/, "English i18n must include Edit member CTA");
assert.match(enSource, /"editMemberTitle"/, "English i18n must include Edit member title");
assert.match(enSource, /"displayName"/, "English i18n must include display name field");
assert.match(enSource, /"phone"/, "English i18n must include phone field");
assert.match(enSource, /"address"/, "English i18n must include address field");
assert.match(enSource, /"resetPassword"/, "English i18n must include reset password CTA");
assert.match(enSource, /"copyNewLink"/, "English i18n must include copy new invite link CTA");
assert.match(enSource, /"roleHints"/, "English i18n must include role hint copy");
assert.match(enSource, /"searchPlaceholder"/, "English i18n must include search placeholder");
assert.match(enSource, /"directoryEyebrow"/, "English i18n must include directory eyebrow copy");

assert.match(globalCssSource, /\.ops-users-canvas/, "Global CSS must style Users canvas");
assert.match(globalCssSource, /\.ops-users-drawer/, "Global CSS must style edit drawer");
assert.match(globalCssSource, /\.ops-users-toolbar/, "Global CSS must style Users toolbar");
assert.match(globalCssSource, /\.ops-users-modal/, "Global CSS must style Users modal");
assert.match(globalCssSource, /\.ops-users-role-chip/, "Global CSS must style role chips");

const pageExists = readFileSync(join(repoRoot, "apps/web/src/app/ops/users/page.tsx"), "utf8");
assert.match(pageExists, /pageMetadata\.opsUsers/, "Users route must use opsUsers metadata");
assert.doesNotMatch(pageExists, /OpsConsoleShell/, "Route must not double-wrap OpsConsoleShell");

console.log("ops-users tests passed");
