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

assert.match(pageSource, /OpsConsoleShell/, "Users page must own Ops shell so refresh can live in the topbar");
assert.match(pageSource, /TopbarRefreshButton/, "Users page must use icon refresh in the topbar");
assert.doesNotMatch(pageSource, /OpsPageHeader/, "Users page must not duplicate shell title with OpsPageHeader");
assert.match(pageSource, /ops-users-toolbar/, "Members toolbar must host search/filter/invite");
assert.match(pageSource, /ops-users-modal/, "Invite/Edit must use a modal dialog");
assert.match(pageSource, /ops-users-canvas/, "Users page must use a distinctive canvas surface");
assert.match(pageSource, /ops-users-hero/, "Users page must open with a hero access strip");
assert.match(pageSource, /ops-users-roster/, "Members must render in a roster table surface");
assert.match(pageSource, /ops-users-role-chip/, "Roles must use distinctive role chips");
assert.match(pageSource, /opsUsers\.inviteMember|opsUsers\.addMember/, "Primary add CTA must be Invite member");
assert.match(pageSource, /opsUsers\.editMember|opsUsers\.edit/, "Row must expose Edit action");
assert.match(pageSource, /opsUsers\.removeMember|opsUsers\.remove/, "Row must expose Remove soft-delete action");
assert.match(pageSource, /window\.confirm|ops-users-confirm/, "Disable/Remove must confirm before applying");
assert.match(pageSource, /searchQuery|setSearchQuery/, "Members list must support search");
assert.match(pageSource, /roleFilter|setRoleFilter/, "Members list must support role filter");
assert.match(pageSource, /ops-users-pending/, "Pending invites must be a secondary panel under the toolbar");
assert.doesNotMatch(pageSource, /ops-users-aside/, "Invite form must not permanently occupy a left column");
assert.match(pageSource, /\/auth\/invite\?token=/, "Users page must build invite accept link");

assert.match(enSource, /"inviteMember"/, "English i18n must include Invite member CTA");
assert.match(enSource, /"editMember"/, "English i18n must include Edit member CTA");
assert.match(enSource, /"removeMember"/, "English i18n must include Remove member CTA");
assert.match(enSource, /"searchPlaceholder"/, "English i18n must include search placeholder");
assert.match(enSource, /"directoryEyebrow"/, "English i18n must include directory eyebrow copy");

assert.match(globalCssSource, /\.ops-users-canvas/, "Global CSS must style Users canvas");
assert.match(globalCssSource, /\.ops-users-hero/, "Global CSS must style Users hero");
assert.match(globalCssSource, /\.ops-users-roster/, "Global CSS must style Users roster");
assert.match(globalCssSource, /\.ops-users-toolbar/, "Global CSS must style Users toolbar");
assert.match(globalCssSource, /\.ops-users-modal/, "Global CSS must style Users modal");
assert.match(globalCssSource, /\.ops-users-role-chip/, "Global CSS must style role chips");

const pageExists = readFileSync(join(repoRoot, "apps/web/src/app/ops/users/page.tsx"), "utf8");
assert.match(pageExists, /pageMetadata\.opsUsers/, "Users route must use opsUsers metadata");
assert.doesNotMatch(pageExists, /OpsConsoleShell/, "Route must not double-wrap OpsConsoleShell");

console.log("ops-users tests passed");
