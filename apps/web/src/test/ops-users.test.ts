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

assert.match(pageSource, /OpsConsoleShell/, "Users page must own the Ops shell");
assert.match(pageSource, /TopbarRefreshButton/, "Refresh must remain in the Ops topbar");
assert.doesNotMatch(pageSource, /OpsPageHeader/, "Users page must not duplicate the shell title");
assert.match(pageSource, /<section className="ops-users-command-table"/, "Users must use the flat Command Table concept");
assert.match(pageSource, /<table className="ops-users-command-table__table">/, "Members must use a semantic HTML table");
assert.match(pageSource, /ops-users-command-table__command[\s\S]*ops-users-search[\s\S]*setRoleFilter[\s\S]*setAccessFilter/, "Search and filters must share one command bar");
assert.match(pageSource, /ops-users-command-table__tabs[\s\S]*summary\.total[\s\S]*summary\.pending/, "Member and invite views must expose truthful backend counts");
assert.match(pageSource, /criticalSignalCount \+ watchSignalCount > 0[\s\S]*signalsNeedReview/, "Review count must only render when a real signal exists");
assert.match(pageSource, /toggleMemberSort[\s\S]*memberSortDirection/, "Directory columns must support deterministic client-side sorting");
assert.match(pageSource, /sortedFilteredMembers\.map[\s\S]*primarySignalKind[\s\S]*ops-users-command-review/, "Each member row must derive its review state from real member data");
assert.match(pageSource, /className=\{`ops-users-command-row is-\$\{primarySignalKind \?\? "clear"\}/, "Review severity must also drive the row rail");
assert.match(pageSource, /ops-users-command-identity[\s\S]*onClick=\{\(\) => openEditDrawer\(member\)\}/, "Clicking member identity must open the edit drawer directly");
assert.match(pageSource, /ops-users-command-access[\s\S]*ops-tts-setup-switch[\s\S]*checked=\{member\.isActive\}/, "Access must remain an inline switch bound to backend state");
assert.match(pageSource, /ops-users-command-session[\s\S]*member\.lastSeenAt[\s\S]*member\.createdAt/, "Session cell must show last sign-in and joined dates");
assert.match(pageSource, /String\(date\.getDate\(\)\)\.padStart[\s\S]*String\(date\.getMonth\(\) \+ 1\)\.padStart/, "Roster dates must use deterministic numeric formatting");
assert.match(pageSource, /ops-users-command-invite-table/, "Invitations must use the matching Command Table model");
assert.match(pageSource, /filteredInvites/, "Pending invites must share search and role filtering");
assert.match(pageSource, /invite\.createdAt/, "Invitations must show when they were created");

assert.doesNotMatch(pageSource, /ops-users-permission-grid|ops-users-permission-table|ops-users-permission-role/, "The rejected Permission Grid must stay retired");
assert.doesNotMatch(pageSource, /selectedMemberId|ops-users-permission-grid__selection/, "The distracting selected-member toolbar must stay retired");
assert.doesNotMatch(pageSource, /ops-users-attention/, "The extra attention banner must stay retired");
assert.doesNotMatch(pageSource, /ROLE_OPTIONS\.map\(\(role\)[\s\S]*role-track/, "Rows must not repeat a four-column role matrix");
assert.doesNotMatch(pageSource, /lastSignInPosition|signInPosition/, "The rejected sign-in micro timeline must stay retired");
assert.doesNotMatch(pageSource, /groupByRole|ledgerGroups|collapsedRoles|expandedMemberId|ops-users-ledger/, "People Ledger grouping must stay retired");
assert.doesNotMatch(pageSource, /ops-users-identity-atlas|ops-users-access-matrix|ops-users-atlas-node|ops-users-matrix-row/, "Atlas and Access Matrix layouts must stay retired");
assert.doesNotMatch(pageSource, /ops-users-v2-command|ops-users-v3-strip|ops-users-board-shell|ops-users-role-board|ops-users-lane-member/, "Previous KPI and role-lane layouts must stay retired");
assert.doesNotMatch(pageSource, /ops-users-gallery|ops-users-deck|ops-users-card/, "Card-gallery layouts must stay retired");
assert.doesNotMatch(pageSource, /ops-users-atelier|ops-users-band|ops-users-split|ops-users-inspect/, "Split and atelier layouts must stay retired");
assert.doesNotMatch(pageSource, /ops-users-masthead|ops-users-seg|ops-users-person|ops-users-metrics|ops-users-rail/, "Decorative legacy layouts must stay retired");

assert.match(globalCssSource, /\.ops-users-command-table__table\s*\{[^}]*table-layout:\s*fixed/, "Command Table must keep a stable fixed layout");
assert.match(globalCssSource, /\.ops-users-command-row\s*\{[^}]*content-visibility:\s*auto/, "Large directories must skip off-screen row rendering");
assert.match(globalCssSource, /\.ops-users-command-table__table\s*>\s*thead\s*\{[^}]*position:\s*sticky/, "Column labels must remain sticky while scanning");
assert.match(globalCssSource, /\.ops-users-command-row\s+td:first-child\s*\{[^}]*position:\s*sticky/, "Member identity must remain sticky during horizontal scrolling");
assert.match(globalCssSource, /\.ops-users-command-row\s+td:first-child::before\s*\{[^}]*width:\s*3px/, "Each row must expose a compact review-severity rail");
assert.match(globalCssSource, /\.ops-users-command-review\.is-disabled[\s\S]*\.ops-users-command-review\.is-unseen[\s\S]*\.ops-users-command-review\.is-owner/, "Review signals must have distinct visual states");
assert.match(globalCssSource, /@media \(max-width:\s*760px\)[\s\S]*?\.ops-users-command-table__table\s*\{[^}]*min-width:\s*900px/, "Mobile must preserve a horizontally scannable table");

assert.match(pageSource, /protectedOwner/, "Last active owner must be visibly protected");
assert.match(pageSource, /selfDisableBlocked|operatorId === me\?\.operatorId/, "Users UI must prevent self-disable lockout");
assert.match(pageSource, /ops-users-drawer/, "Edit member must use a side drawer");
assert.match(pageSource, /ops-users-drawer__body/, "Edit drawer body must scroll separately from its chrome");
assert.match(pageSource, /ops-users-drawer__footer/, "Edit drawer must pin Cancel and Save actions");
assert.match(pageSource, /ops-users-switch/, "Drawer access control must use a custom switch");
assert.match(pageSource, /ops-users-email-readonly/, "Email must remain read-only identity text");
assert.match(pageSource, /ops-users-modal/, "Invite must use a modal dialog");
assert.match(pageSource, /ops-users-modal-heading[\s\S]*OpsUsersUiIcon kind="invite"/, "Invite modal must use a purposeful identity icon and stacked heading");
assert.match(pageSource, /ops-users-modal-close[\s\S]*OpsUsersUiIcon kind="close"/, "Invite modal must expose an icon close action");
assert.match(pageSource, /ops-users-form-label[\s\S]*kind="mail"[\s\S]*kind="access"/, "Invite fields must use meaningful label icons");
assert.match(pageSource, /leadingIcon=\{<OpsUsersUiIcon kind="send" \/>\}/, "Create invite action must use a send icon");
assert.match(pageSource, /ops-users-section-icon[\s\S]*kind="profile"[\s\S]*kind="access"[\s\S]*kind="security"/, "Edit drawer sections must have distinct semantic icons");
assert.match(pageSource, /leadingIcon=\{<OpsUsersUiIcon kind="security" \/>\}[\s\S]*resetPassword/, "Reset password action must use a security icon");
assert.match(pageSource, /leadingIcon=\{<OpsUsersUiIcon kind="save" \/>\}[\s\S]*saveChanges/, "Save changes action must use a confirmation icon");
assert.match(pageSource, /ops-users-overlay-btn is-secondary[\s\S]*kind="cancel"/, "Overlay cancel actions must use a directional icon");
assert.match(pageSource, /opsUsers\.inviteMember|opsUsers\.addMember/, "Primary CTA must invite a member");
assert.match(pageSource, /aria-label=\{t\("opsUsers\.editMember"\)\}/, "Edit must expose an accessible icon action");
assert.doesNotMatch(pageSource, /sortedFilteredMembers\.map[\s\S]*?\{t\("opsUsers\.enable"\)\}/, "Rows must not show an Enable text button");
assert.doesNotMatch(pageSource, /sortedFilteredMembers\.map[\s\S]*?\{t\("opsUsers\.disable"\)\}/, "Rows must not show a Disable text button");
assert.match(pageSource, /editDisplayName|displayName/, "Edit drawer must support display name");
assert.match(pageSource, /editPhone|phone/, "Edit drawer must support phone");
assert.match(pageSource, /editAddress|address/, "Edit drawer must support address");
assert.match(pageSource, /editNotes|notes/, "Edit drawer must support notes");
assert.match(pageSource, /editActive|accessActive/, "Edit drawer must support access toggle");
assert.match(pageSource, /roleHints/, "Edit drawer must explain role implications");
assert.match(pageSource, /resetWorkspaceMemberPassword|resetPassword/, "Edit drawer must support password reset");
assert.match(pageSource, /rotateWorkspaceInvite|copyNewLink/, "Invites must support rotating and copying a fresh link");
assert.match(pageSource, /window\.confirm/, "Risky access actions must confirm before applying");
assert.match(pageSource, /\/auth\/invite\?token=/, "Users page must build the invite acceptance link");

assert.match(enSource, /"inviteMember"/, "English i18n must include Invite member");
assert.match(enSource, /"editMemberTitle"/, "English i18n must include Edit member title");
assert.match(enSource, /"roleHints"/, "English i18n must include role help");
assert.match(enSource, /"searchPlaceholder"/, "English i18n must include search copy");
assert.match(enSource, /"sessionTimeline"[\s\S]*"accessReview"[\s\S]*"stableShort"/, "English i18n must cover Command Table columns and stable state");
assert.match(enSource, /"signalsNeedReview"[\s\S]*"showingCount"[\s\S]*"showingInvites"/, "English i18n must cover truthful Command Table counts");

assert.match(globalCssSource, /\.ops-users-command-table\s*\{/, "Global CSS must style the Command Table surface");
assert.match(globalCssSource, /\.ops-users-command-table__command/, "Global CSS must style the unified command bar");
assert.match(globalCssSource, /\.ops-users-command-table__viewport/, "Global CSS must style the scalable viewport");
assert.match(globalCssSource, /\.ops-users-command-invite-table/, "Global CSS must style the invitation table");
assert.match(globalCssSource, /\.ops-users-drawer/, "Global CSS must style the edit drawer");
assert.match(globalCssSource, /\.ops-users-modal/, "Global CSS must style the invite modal");
assert.match(globalCssSource, /Ops Users V13[\s\S]*\.ops-users-modal-heading/, "Global CSS must style the polished modal hierarchy");
assert.match(globalCssSource, /\.ops-users-section--access[\s\S]*\.ops-users-section--security/, "Drawer access and security sections must have distinct visual treatments");
assert.match(globalCssSource, /\.ops-users-overlay-btn\.primary[\s\S]*linear-gradient/, "Primary overlay actions must have elevated button chrome");

const pageExists = readFileSync(join(repoRoot, "apps/web/src/app/ops/users/page.tsx"), "utf8");
assert.match(pageExists, /pageMetadata\.opsUsers/, "Users route must use opsUsers metadata");
assert.doesNotMatch(pageExists, /OpsConsoleShell/, "Route must not double-wrap OpsConsoleShell");

console.log("ops-users tests passed");
