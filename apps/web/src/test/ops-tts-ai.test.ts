import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { formatProviderError } from "../lib/opsTranslationAiFormat";
import { formatTtsProbeSuccess } from "../lib/opsTtsTestFormat";
import {
  deriveTtsInstallFromRepoUrl,
  getLocalInstallRecipe,
  resolveTtsProviderKind,
  showsTtsApiKey,
  showsTtsBaseUrl,
  showsTtsLocalBackend
} from "../lib/opsTtsProviderCatalog";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../app/ops/tts-ai/page.tsx"), "utf8");
const componentSource = readFileSync(resolve(testDir, "../components/ops-console/OpsTtsAiPage.tsx"), "utf8");
const catalogSource = readFileSync(resolve(testDir, "../lib/opsTtsProviderCatalog.ts"), "utf8");
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");
const navSource = readFileSync(resolve(testDir, "../lib/navigationConfig.ts"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");
const viSource = readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8");

assert.match(pageSource, /OpsTtsAiPage/, "Route must mount OpsTtsAiPage");
assert.match(componentSource, /fetchTtsAi/, "UI must load TTS AI via API");
assert.match(componentSource, /saveTtsAiProfile/, "UI must save TTS AI via profile API");
assert.match(componentSource, /testTtsAi/, "UI must test TTS AI via API");
assert.match(componentSource, /ops-tts-kind-tabs/, "Must expose provider kind tabs");
assert.match(componentSource, /sectionInstall/, "Local kind must surface install section");
assert.match(componentSource, /copyInstallCommand/, "Must support copy install command");
assert.match(componentSource, /installTtsAiPackage/, "Must one-click install via API");
assert.match(componentSource, /onInstall/, "Must expose Install action");
assert.match(componentSource, /customProviderSlug/, "Must support custom Local/SDK provider name");
assert.match(componentSource, /!editingProfileId && nextKind === "local"/, "New Local drafts must not auto-select Edge");
assert.match(componentSource, /providerChoice:\s*""/, "New Local drafts must preserve an explicit unselected provider state");
assert.match(componentSource, /localDraftNeedsProvider/, "New Local drafts must expose a provider gate");
assert.match(componentSource, /ops-tts-provider-gate/, "Provider gate must explain why dependent sections are hidden");
assert.match(componentSource, /isLocal && !localDraftNeedsProvider/, "Install must wait for a selected Local provider");
assert.match(
  componentSource,
  /\(isLocal \|\| isCloud \|\| isHttp\) && !localDraftNeedsProvider/,
  "Voice and Preview must wait for a selected Local provider"
);
assert.match(enSource, /"providerRequiredTitle"/, "English copy must explain the new-provider gate");
assert.match(viSource, /"providerRequiredTitle"/, "Vietnamese copy must explain the new-provider gate");
assert.match(componentSource, /resolveTtsReadyState/, "Must map Install+Test to ready chip");
assert.match(componentSource, /data-ready-state/, "Must expose ready state on chip");
assert.match(componentSource, /result\.catalog/, "Must apply Test catalog to Voice select");
assert.match(
  componentSource,
  /resolveTtsCatalogForProvider/,
  "Opening a saved setup must resolve persisted or curated provider catalog"
);
assert.match(componentSource, /onRefreshCatalog/, "Editor must expose an explicit catalog refresh action");
assert.match(componentSource, /CatalogRefreshPhase/, "Catalog refresh must have explicit lifecycle phases");
assert.match(componentSource, /setCatalogRefreshPhase\("preparing"\)/, "Catalog refresh must render pre-loading state");
assert.match(componentSource, /setCatalogRefreshPhase\("loading"\)/, "Catalog refresh must render API loading state");
assert.match(componentSource, /data-phase=\{catalogRefreshPhase\}/, "Refresh control must expose its current phase");
assert.match(componentSource, /aria-busy=\{catalogRefreshBusy\}/, "Refresh control must announce busy state");
assert.match(enSource, /"catalogPreparing"/, "English copy must define catalog pre-loading state");
assert.match(viSource, /"catalogLoading"/, "Vietnamese copy must define catalog loading state");
assert.match(cssSource, /\.ops-tts-catalog-refresh\.is-preparing/, "Pre-loading must have distinct visual feedback");
assert.match(cssSource, /\.ops-tts-catalog-refresh\.is-loading/, "Loading must animate the refresh icon");
assert.match(
  componentSource,
  /ops-tts-section__head--with-action[\s\S]*?onRefreshCatalog\(\)[\s\S]*?<svg/,
  "Voice catalog refresh must sit in the section header and include an icon"
);
assert.match(
  componentSource,
  /\{catalog \? \([\s\S]*?ops-tts-status ops-tts-status--compact/,
  "Catalog metadata row must render only when metadata exists"
);
assert.match(cssSource, /\.ops-tts-section__head--with-action/, "Voice header action must have responsive layout styles");
assert.match(componentSource, /fetchTtsAiEngines/, "OmniVoice editor must load the host-aware engine catalog");
assert.match(componentSource, /installTtsAiEngine/, "OmniVoice editor must support registry-owned dependency installs");
assert.match(componentSource, /onInstallEngine/, "OmniVoice engine rows must expose their install action");
assert.match(componentSource, /fetchTtsAiEngineInstallStatus/, "Engine installs must reattach and poll durable status");
assert.match(componentSource, /engineInstallJob/, "Engine cards must retain active install state");
assert.match(componentSource, /<progress max=\{100\}/, "Engine cards must render one-click install progress");
assert.match(componentSource, /disabled=\{!engine\.selectable\}/, "Engines without a synthesize adapter must remain unselectable");
assert.match(componentSource, /engineExpandedId/, "Manual and external engines must expose progressive setup guidance");
assert.match(componentSource, /engineSetupGuide/, "Manual engines must render an explicit setup-guide action");
assert.match(componentSource, /engineDependencyLabelKey/, "Every compact engine row must retain dependency status text");
assert.match(apiSource, /\/ops\/tts-ai\/engines/, "API client must expose the OmniVoice engine catalog endpoint");
assert.match(enSource, /"engineCatalogTitle"/, "en.json must define the OmniVoice engine catalog title");
assert.match(viSource, /"engineCatalogTitle"/, "vi.json must define the OmniVoice engine catalog title");
assert.match(enSource, /"engineInstall": "Install engine"/, "English action must describe the full engine install");
assert.match(viSource, /"engineInstall": "Cài engine"/, "Vietnamese action must describe the full engine install");
assert.match(componentSource, /engineCatalogCategory/, "Engine catalog must derive one clear state per engine");
assert.match(componentSource, /engineGroups/, "Engine catalog must group models by operational state");
assert.match(componentSource, /engineGroupTab/, "Engine categories must retain the selected tab");
assert.match(componentSource, /role="tablist"/, "Engine categories must use an accessible tab list");
assert.match(componentSource, /role="tabpanel"/, "The selected engine category must render a tab panel");
assert.match(componentSource, /aria-selected=\{engineGroupTab === group\.id\}/, "Engine tabs must expose selection state");
assert.match(componentSource, /ops-tts-engine-catalog__meta/, "Engine totals must stay in the compact catalog header");
assert.match(componentSource, /ops-tts-engine-card__row/, "Each engine must use a compact single-row card");
assert.match(componentSource, /ops-tts-engine-card__controls/, "Only actionable controls should occupy card space");
assert.match(componentSource, /ops-tts-engine-card__identity-top/, "Compact cards must align title and size cleanly");
assert.match(componentSource, /ops-tts-engine-card__details-toggle[\s\S]*?<svg/, "Details must use a quiet icon control");
assert.match(componentSource, /EngineCatalogActionIcon/, "Engine actions must use dedicated visual icons");
assert.match(componentSource, /ops-tts-engine-card__action is-icon/, "Install and setup actions must be icon-only");
assert.match(componentSource, /aria-label=\{installActionLabel\}/, "Icon-only install action must remain accessible");
assert.match(componentSource, /title=\{guideActionLabel\}/, "Icon-only setup action must expose a tooltip");
assert.doesNotMatch(componentSource, /engineFilters|engineSearch/, "Compact catalog must not add filter or search chrome");
assert.match(cssSource, /\.ops-tts-engine-card__identity/, "Compact cards must style their condensed identity block");
assert.match(cssSource, /\.ops-tts-engine-tabs/, "Engine category tabs must use compact segmented styling");
assert.match(cssSource, /\.ops-tts-engine-card:hover/, "Engine cards must have restrained interactive polish");
assert.match(cssSource, /\.ops-tts-engine-card__progress/, "Engine install progress must have a compact card treatment");
assert.match(cssSource, /repeat\(3, minmax\(0, 1fr\)\)/, "Wide engine catalog must use a compact three-column layout");
assert.match(componentSource, /voiceFromCatalog/, "Must explain catalog-backed voices");
assert.match(componentSource, /previewTtsAiSpeech/, "Must support speech preview");
assert.match(componentSource, /fetchTtsAiPreviewStatus/, "Must poll async TTS preview status");
assert.match(componentSource, /cancelTtsAiPreview/, "Must support cancel TTS preview");
assert.match(componentSource, /onCancelPreview/, "Must expose Stop preview action");
assert.match(componentSource, /ops-tts-editor\b/, "Editor must use editor layout root");
assert.match(componentSource, /ops-header-actions ops-ai-toolbar/, "Editor toolbar must match AI settings chrome");
assert.match(componentSource, /ops-ai-meta/, "Editor status must sit in OpsPanel meta");
assert.match(componentSource, /ops-tts-section/, "Editor must use stacked TTS section cards");
assert.match(componentSource, /ops-tts-section--install/, "Editor must include Install section");
assert.match(componentSource, /ops-tts-section--preview/, "Editor must include Preview section");
assert.doesNotMatch(componentSource, /ops-ai-howto|ops-tts-steps/, "How it works must be removed from TTS editor");
assert.doesNotMatch(
  componentSource,
  /ops-tts-studio|ops-tts-bento|ops-tts-editor-aside|ops-tts-preview-deck|ops-tts-provider-rail|ops-tts-workbench/,
  "Experimental mosaic/studio shells must be retired"
);
assert.match(componentSource, /ops-tts-kind-tabs--segmented/, "Kind tabs must be segmented");
assert.match(componentSource, /ops-tts-install-command-bar/, "Install must use command bar");
assert.match(componentSource, /ops-tts-action-btn/, "Install/Preview action buttons must use icon + text");
assert.match(componentSource, /kind=\"copy\"/, "Copy install must use copy icon");
assert.match(componentSource, /kind=\"install\"/, "Install must use install icon");
assert.match(componentSource, /kind=\"reinstall\"/, "Reinstall must use reinstall icon");
assert.match(componentSource, /kind=\"preview\"/, "Preview must use preview icon");
assert.match(componentSource, /kind=\"stop\"/, "Preview cancel must use stop icon");
assert.match(componentSource, /ops-tts-editor-actions__label/, "Action buttons must wrap short text labels");
assert.match(cssSource, /\.ops-tts-action-btn\b/, "CSS must style icon + text action buttons");
assert.match(cssSource, /\.ops-tts-editor\.is-dense\b/, "CSS must support denser TTS form spacing");
assert.match(componentSource, /ops-tts-field-hint--quiet/, "Long field hints must be quiet until focus");
assert.match(componentSource, /ops-tts-section--advanced/, "Advanced settings must be an always-open section");
assert.doesNotMatch(
  componentSource,
  /<details className="ops-tts-advanced"/,
  "Advanced must not use a collapsible details block"
);
assert.match(componentSource, /opsTtsAi\.setupName/, "Editor must expose Setup name (profile name)");
assert.match(componentSource, /id="tts-ai-setup-name"/, "Setup name must be an editable field in the editor");
assert.match(componentSource, /opsTtsAi\.provider/, "Provider field must use Provider label (not Name Provider)");
assert.match(componentSource, /ops-tts-provider-name/, "Provider field must use dedicated class");
assert.match(
  componentSource,
  /<select[\s\n]+id="tts-ai-provider"/,
  "Provider must be a select dropdown by kind"
);
assert.doesNotMatch(
  componentSource,
  /<input[\s\n]+id="tts-ai-provider"/,
  "Provider must not be a free-text Name Provider input"
);
assert.match(
  componentSource,
  /id="tts-ai-custom-slug"/,
  "Local Custom must expose a separate custom slug field"
);
assert.match(componentSource, /function onProviderSelect/, "Provider select must have a change handler");
assert.match(componentSource, /function onCustomSlugInput/, "Custom slug must have a typed handler");
assert.doesNotMatch(componentSource, /function onProviderNameInput/, "Free-text Name Provider handler must be removed");
assert.match(componentSource, /providerHint/, "Provider select must show a hint");
assert.doesNotMatch(componentSource, /ops-tts-install-more/, "Install extras must not use a collapsible details block");
assert.doesNotMatch(componentSource, /installMoreOptions/, "Install more-options accordion label must be removed");
assert.match(componentSource, /id="tts-ai-package"/, "Package name must stay on the Install form");
assert.match(componentSource, /id="tts-ai-repo"/, "Repo URL must stay on the Install form");
assert.match(componentSource, /id="tts-ai-extra"/, "Extra requirements must stay on the Install form");
assert.match(
  componentSource,
  /ops-tts-section--install[\s\S]*?ops-tts-grid[\s\S]*?tts-ai-package/,
  "Package/repo/extras must sit in the Install section grid, always visible"
);
assert.match(componentSource, /sectionAdvancedHint/, "Advanced hint copy key must be referenced");
assert.match(
  componentSource,
  /function blankForm\(\)[\s\S]*?timeoutSeconds:\s*""[\s\S]*?fallbackProvider:\s*""/,
  "New blank form must not seed Advanced defaults"
);
assert.match(componentSource, /fallbackProviderPlaceholder/, "Fallback provider must expose placeholder copy");
assert.match(componentSource, /fallbackProviderHint/, "Fallback provider must expose hint copy");
assert.match(enSource, /"sectionAdvancedHint"/, "en i18n must define sectionAdvancedHint");
assert.match(viSource, /"sectionAdvancedHint"/, "vi i18n must define sectionAdvancedHint");
assert.match(enSource, /"fallbackProviderPlaceholder"/, "en i18n must define fallback provider placeholder");
assert.match(viSource, /"fallbackProviderPlaceholder"/, "vi i18n must define fallback provider placeholder");
assert.match(enSource, /"localBackendPlaceholder"/, "en i18n must define local backend placeholder");
assert.match(enSource, /"devicePlaceholder"/, "en i18n must define device placeholder");
assert.match(enSource, /"setupName"/, "en i18n must define Setup name");
assert.match(viSource, /"setupName"/, "vi i18n must define Setup name");
assert.match(enSource, /"provider": "Provider"/, "en i18n must define Provider label");
assert.match(viSource, /"provider"/, "vi i18n must define Provider label");
assert.match(enSource, /"providerHint"/, "en i18n must define Provider hint");
assert.match(viSource, /"providerHint"/, "vi i18n must define Provider hint");
assert.match(enSource, /"providerCustom"/, "en i18n must define Custom provider option");
assert.match(
  componentSource,
  /kind === "local"[\s\S]*?tts-ai-custom-slug|tts-ai-custom-slug[\s\S]*?kind === "local"/,
  "Custom slug field must only appear for Local Custom"
);
assert.match(
  componentSource,
  /TTS_PROVIDERS_BY_KIND\[kind\]/,
  "Provider select options must come from the kind catalog"
);
assert.match(
  componentSource,
  /placeholder=\{t\("opsTtsAi\.(installCommandPlaceholder|packageNamePlaceholder|repoUrlPlaceholder|extraRequirementPlaceholder|baseUrlPlaceholder|apiKeyPlaceholder|voiceOptionalPlaceholder|voiceIdPlaceholder|speakingRatePlaceholder|languageCodePlaceholder|modelIdPlaceholder|previewTextPlaceholder|timeoutSecondsPlaceholder|fallbackVoiceIdPlaceholder|cliBinaryPlaceholder|setupNamePlaceholder|customProviderSlugPlaceholder)"\)/,
  "Editor text inputs must use i18n placeholder keys"
);
assert.match(
  componentSource,
  /opsTtsAi\.(providerHint|installCommandHint|packageNameHint|repoUrlHint|extraRequirementHint|baseUrlHint|apiKeyHint|speakingRateHint|languageCodeHint|modelIdHint|previewTextHint|timeoutSecondsHint|fallbackVoiceIdHint|cliBinaryHint|setupNameHint|customProviderHint)/,
  "Editor fields must expose field hints"
);
assert.match(
  componentSource,
  /function blankForm\(\)[\s\S]*?installCommand:\s*""[\s\S]*?packageName:\s*""/,
  "Placeholders must not replace empty New draft values"
);
assert.match(cssSource, /\.ops-tts-section\b/, "CSS must style TTS section cards");
assert.match(cssSource, /\.ops-ai-toolbar\b/, "CSS must style AI toolbar chrome");
assert.match(cssSource, /\.ops-tts-install-command-bar\b/, "CSS must style install command bar");
assert.match(cssSource, /\.ops-tts-field-hint--quiet\b/, "CSS must hide quiet field hints until focus");
assert.match(cssSource, /\.ops-tts-section--advanced\b/, "CSS must style always-open Advanced section");
assert.match(cssSource, /\.ops-tts-provider-name\b/, "CSS must style Provider field");
assert.doesNotMatch(cssSource, /\.ops-tts-studio\b|\.ops-tts-bento\b/, "Studio/bento mosaic CSS must be removed");
assert.match(componentSource, /sectionPreview/, "Must expose Preview speech section");
assert.match(componentSource, /ops-tts-preview-bar/, "Preview controls must sit in one bar");
assert.match(componentSource, /previewValidationMessage/, "Preview must validate provider configuration before API calls");
assert.match(componentSource, /previewCloudUnavailable/, "Unsupported Cloud preview must use friendly guidance");
assert.match(componentSource, /showPreviewFailure/, "Preview failures must use panel-local feedback");
assert.match(componentSource, /ops-tts-preview-feedback/, "Preview panel must render its own error banner");
assert.match(cssSource, /\.ops-tts-preview-feedback/, "Preview feedback must have dedicated styling");
assert.match(enSource, /"previewBlockedTitle"/, "English copy must define the Preview validation banner");
assert.match(viSource, /"previewCloudUnavailable"/, "Vietnamese copy must explain unavailable Cloud preview");
{
  const previewStart = componentSource.indexOf("async function onPreview(");
  const previewEnd = componentSource.indexOf("async function onCancelPreview(", previewStart);
  const previewChunk = componentSource.slice(previewStart, previewEnd > previewStart ? previewEnd : undefined);
  assert.doesNotMatch(
    previewChunk,
    /setError\((?:status\.detail|started\.detail|message)\)/,
    "Preview must not dump raw provider errors into the page-top inline error"
  );
}
assert.match(componentSource, /createTtsAiProfile/, "Must create TTS setup via API on Save");
assert.match(
  componentSource,
  /async function onSave\([\s\S]*?createTtsAiProfile/,
  "Save must create a new setup when editing a draft"
);
assert.match(
  componentSource,
  /async function onSave\([\s\S]*?renameTtsAiProfile/,
  "Save must rename an existing setup when Setup name changed"
);
assert.doesNotMatch(
  componentSource,
  /async function onCreateProfile\([\s\S]*?createTtsAiProfile/,
  "New must open a draft form without creating a setup"
);
assert.match(
  componentSource,
  /function blankForm\(\)[\s\S]*?installCommand:\s*""[\s\S]*?packageName:\s*""/,
  "New blank form must start with empty install/package fields"
);
assert.match(
  componentSource,
  /function blankForm\(\)[\s\S]*?voiceId:\s*""[\s\S]*?speakingRate:\s*""[\s\S]*?languageCode:\s*""/,
  "New blank form must not seed voice/rate/lang example values"
);
assert.doesNotMatch(
  componentSource,
  /function applyProvider\([\s\S]*?patch\.voiceId\s*=\s*nextRecipe/,
  "Choosing a provider must not auto-fill voice from install recipe"
);
assert.doesNotMatch(
  componentSource,
  /function applyProvider\([\s\S]*?patch\.installCommand\s*=\s*nextRecipe/,
  "Choosing a provider must not auto-fill install command from recipe"
);
assert.doesNotMatch(
  componentSource,
  /function applyProvider\([\s\S]*?patch\.packageName\s*=\s*nextRecipe/,
  "Choosing a provider must not auto-fill package name from recipe"
);
assert.doesNotMatch(
  componentSource,
  /function applyProvider\([\s\S]*?patch\.extraRequirement\s*=\s*nextRecipe/,
  "Choosing a provider must not auto-fill extras from recipe"
);
assert.doesNotMatch(
  componentSource,
  /function applyProvider\([\s\S]*?patch\.baseUrl\s*=\s*"https:\/\/api\.openai\.com/,
  "Choosing a provider must not auto-fill Base URL examples"
);
assert.match(
  componentSource,
  /function onKindChange\([\s\S]*?defaultProviderForKind/,
  "Kind tabs may seed the first catalog provider into the Provider select"
);
assert.match(componentSource, /function nextBlankSetupName/, "New/Save must auto-name blank setups");
assert.match(componentSource, /activateTtsAiProfile/, "Must switch active TTS setup via API");
assert.match(componentSource, /renameTtsAiProfile/, "Must rename TTS setup via API");
assert.match(componentSource, /deleteTtsAiProfile/, "Must delete TTS setup via API");
assert.match(componentSource, /setTtsAiProfileEnabled/, "Must toggle enabled on overview");
assert.match(componentSource, /saveTtsAiProfile/, "Must save editor via profile PUT");
assert.match(componentSource, /api_key_masked/, "Profile editing must preserve masked API key metadata");
assert.match(componentSource, /ops-ai-voice-runtime-cell/, "Voice runtime must keep credential state visually grouped");
assert.match(componentSource, /showsTtsApiKey\(profile\.provider\)/, "Credential state must only render for providers that require an API key");
assert.match(apiSource, /api_key_masked/, "Profile summary type must include api_key_masked");
assert.match(componentSource, /viewMode === \"list\"/, "Must default to list overview");
assert.match(componentSource, /ops-tts-list-toolbar/, "Must expose list toolbar for saved setups");
assert.match(componentSource, /onSetActive/, "Must set active via On/Off on overview");
assert.match(componentSource, /profileEdit/, "Must open editor from overview");
assert.doesNotMatch(componentSource, /ops-tts-profile-bar/, "Dropdown profile bar must not be the overview");
assert.match(apiSource, /\/ops\/tts-ai\/preview/, "API helper must hit preview endpoint");
assert.match(apiSource, /\/ops\/tts-ai\/preview\/status/, "API helper must poll preview status");
assert.match(apiSource, /\/ops\/tts-ai\/preview\/cancel/, "API helper must cancel preview");
assert.match(apiSource, /fetchTtsAiPreviewStatus/, "API helper must export fetchTtsAiPreviewStatus");
assert.match(apiSource, /cancelTtsAiPreview/, "API helper must export cancelTtsAiPreview");
assert.match(apiSource, /\/ops\/tts-ai\/profiles/, "API helper must hit TTS profiles endpoint");
assert.match(apiSource, /createTtsAiProfile/, "API helper must export createTtsAiProfile");
assert.match(apiSource, /activateTtsAiProfile/, "API helper must export activateTtsAiProfile");
assert.match(apiSource, /saveTtsAiProfile/, "API helper must export saveTtsAiProfile");
assert.match(componentSource, /ops-tts-setup-table/, "List must use table layout");
assert.match(componentSource, /ops-ai-control-center is-tts/, "TTS list must use the AI Setup Control Center surface");
assert.match(componentSource, /ops-ai-registry-leading/, "TTS registry must use a voice-specific identity header");
assert.match(componentSource, /ops-ai-registry-table is-tts/, "TTS setups must use the condensed voice registry table");
assert.match(componentSource, /voiceRuntimeCol[\s\S]*speechRuntimeCol[\s\S]*statusControlCol/, "TTS registry must group voice, runtime and control data into single-line columns");
assert.match(componentSource, /ops-ai-voice-runtime-cell[\s\S]*profileKeySet[\s\S]*profileKeyUnset/, "Grouped voice runtime must preserve visible API key state");
assert.match(componentSource, /showsTtsApiKey\(profile\.provider\)/, "Voice runtime must only show key state for providers that require credentials");
assert.match(componentSource, /hasFallback \? `FB:[\s\S]*profile\.fallback_voice_id/, "Fallback voice must not render without a configured fallback provider");
assert.doesNotMatch(componentSource, /hasFallbackColumn/, "Fallback must fold into voice configuration instead of creating a sparse column");
assert.match(componentSource, /ops-ai-inline-config[\s\S]*ops-ai-inline-status/, "TTS rows must use compact single-line data groups");
assert.doesNotMatch(componentSource, /OpsAiProviderMark/, "Setup names must not have decorative leading icons");
assert.match(componentSource, /ops-ai-row-actions/, "Row actions must be wrapped without changing table-cell display");
assert.match(cssSource, /\.ops-ai-registry-table \.ops-ai-row-actions\s*\{[^}]*display:\s*inline-flex/s, "Action wrapper must own flex alignment");
assert.doesNotMatch(cssSource, /\.ops-ai-registry-table \.ops-tts-setup-table__actions\s*\{[^}]*display:\s*flex/s, "Table action cell must retain table-cell layout");
assert.match(cssSource, /\.ops-ai-control-center \.ops-ai-registry-table td\s*\{[^}]*height:\s*56px[^}]*white-space:\s*nowrap/s, "AI registry rows must stay on one compact line");
assert.match(componentSource, /<thead>/, "Table must have column headers");
assert.doesNotMatch(componentSource, /ops-tts-setup-switch__label/, "Active switch must not show On/Off text");
assert.match(componentSource, /ops-tts-setup-switch/, "Table must keep the Active toggle switch");
assert.match(componentSource, /languageCode/, "Table must show language_code column");
assert.match(componentSource, /speakingRate/, "Table must show speaking_rate column");
assert.doesNotMatch(componentSource, /ops-tts-setup-card/, "Card list layout must be replaced by table");
assert.match(componentSource, /TtsSetupActionIcon/, "Edit/Delete must use icon components");
assert.match(componentSource, /ops-tts-setup-table__icon-btn/, "Edit/Delete must be icon buttons");
assert.match(componentSource, /kind=\"delete\"/, "Delete must be an icon action");
assert.match(componentSource, /isOn \? \"is-active\"/, "On row (active+enabled) must get is-active class");
assert.match(
  componentSource,
  /isActive && Boolean\(profile\.enabled\)/,
  "Row highlight must match switch On = active profile and enabled"
);
assert.match(componentSource, /aria-label=\{t\("opsTtsAi\.profileEdit"\)\}/, "Edit icon must keep accessible label");
assert.doesNotMatch(componentSource, /kind=\"rename\"/, "Rename icon button must be removed");
assert.match(componentSource, /ops-tts-setup-table__name-btn/, "Setup name must be clickable to rename");
assert.doesNotMatch(componentSource, /profileRenamePrompt/, "Rename must not use browser prompt copy");
assert.match(componentSource, /renamingProfileId/, "Rename must use inline edit state");
assert.match(componentSource, /ops-tts-setup-table__rename-input/, "Rename must edit name inline in the table");
assert.doesNotMatch(
  componentSource,
  /window\.prompt\(t\("opsTtsAi\.profileNewPrompt/,
  "New must not open a name prompt"
);
assert.match(componentSource, /function nextBlankSetupName/, "New/Save must auto-name blank setups");
assert.match(componentSource, /TopbarRefreshButton/, "TTS page must expose icon refresh in the topbar");
assert.match(componentSource, /OpsConsoleShell/, "TTS page must own OpsConsoleShell so refresh lives in Topbar");
assert.match(componentSource, /ops-tts-list-toolbar/, "List must use toolbar layout instead of OpsPanel heading");
assert.match(componentSource, /ops-tts-list-header/, "List Active/New cluster must sit in list header (top-right)");
assert.doesNotMatch(
  componentSource,
  /clearApiKey|opsTtsAi\.clearApiKey/,
  "TTS must not expose Clear stored API key — keys stay in workspace DB"
);
assert.match(cssSource, /\.ops-tts-list-toolbar/, "CSS must style TTS list toolbar");
assert.match(componentSource, /ops-tts-list-toolbar__cluster/, "Toolbar controls must be grouped");
assert.match(componentSource, /ops-tts-list-toolbar__new/, "New must be a toolbar button");
assert.match(componentSource, /ops-tts-list-toolbar__active/, "Active setup must use the polished toolbar status");
assert.match(
  componentSource,
  /activeOnProfile/,
  "Toolbar Active must derive from enabled active setup (activeOnProfile)"
);
assert.match(
  componentSource,
  /activeOnProfile \? \(/,
  "Toolbar Active badge must hide when all setups are Off"
);
assert.match(componentSource, /ops-tts-list-toolbar__plus/, "Add icon must use the toolbar plus glyph");
assert.match(cssSource, /\.ops-tts-list-toolbar__plus/, "CSS must size the plus icon");
assert.match(componentSource, /kind=\"add\"/, "New action must use a plus/add icon");
{
  const listStart = componentSource.indexOf('viewMode === "list"');
  const listEnd = componentSource.indexOf("if (!form)", listStart);
  const listChunk = componentSource.slice(listStart, listEnd);
  assert.match(
    listChunk,
    /ops-tts-list-toolbar__new[\s\S]*?\{t\("opsTtsAi\.profileNew"\)\}/,
    "List New control must show New text with the plus icon"
  );
}
{
  const listStart = componentSource.indexOf('viewMode === "list"');
  const listEnd = componentSource.indexOf("if (!form)", listStart);
  assert.ok(listStart >= 0 && listEnd > listStart, "Must locate list overview block");
  const listChunk = componentSource.slice(listStart, listEnd);
  assert.doesNotMatch(listChunk, /common\.refresh/, "List panel header must not duplicate text Refresh");
  assert.match(listChunk, /profileNew/, "List header must keep New");
  assert.doesNotMatch(listChunk, /listPanelTitle/, "List must not use OpsPanel list title");
  assert.doesNotMatch(listChunk, /sectionProfilesHint/, "List must not show long setups hint under a panel title");
  assert.doesNotMatch(listChunk, /<OpsPanel/, "List mode must not wrap content in OpsPanel");
}
assert.match(componentSource, /aria-label=\{t\("opsTtsAi\.profileDelete"\)\}/, "Delete icon must keep accessible label");
assert.match(cssSource, /tbody tr\.is-active/, "CSS must highlight active TTS setup row");
assert.match(cssSource, /ops-tts-setup-table__icon-btn--danger/, "CSS must style delete icon as danger");
assert.doesNotMatch(componentSource, /profileSetActive/, "Separate Set active button must be removed");
assert.match(componentSource, /statusControlCol/, "Combined status column must label the On/Off switch");
assert.match(componentSource, /activateTtsAiProfile/, "On/Off On must call activate API");
assert.match(componentSource, /sampleRate/, "Must show sample rate meta from catalog");
assert.match(componentSource, /EDGE_FALLBACK_VOICE_OPTIONS/, "Fallback edge voices must be selectable");
assert.match(componentSource, /styleHint/, "Must clarify reading style vs voice label");
assert.match(componentSource, /ops-header-actions ops-ai-toolbar/, "Editor form must use AI toolbar chrome");
assert.match(componentSource, /ops-ai-toolbar__group/, "Editor must expose Back/Test/Save toolbar group");
assert.match(componentSource, /kind=\"back\"/, "Back button must show back icon");
assert.match(componentSource, /kind=\"test\"/, "Test button must show test icon");
assert.match(componentSource, /kind=\"save\"/, "Save button must show save icon");
assert.match(componentSource, /opsTtsAi\.actionBack/, "Back button must use short Back label");
assert.match(componentSource, /opsTtsAi\.actionTest/, "Test button must use short Test label");
assert.match(componentSource, /opsTtsAi\.actionSave/, "Save button must use short Save label");
assert.match(componentSource, /ops-tts-editor-actions__label/, "Toolbar buttons must wrap short text labels");
assert.match(cssSource, /\.ops-ai-toolbar__group/, "CSS must style AI toolbar group");
assert.match(cssSource, /\.ops-ai-toolbar__group > button/, "Toolbar buttons must support icon + text row");
assert.match(enSource, /"actionBack"\s*:\s*"Back"/, "EN must define short Back label");
assert.match(enSource, /"actionTest"\s*:\s*"Test"/, "EN must define short Test label");
assert.match(enSource, /"actionSave"\s*:\s*"Save"/, "EN must define short Save label");
assert.match(componentSource, /ops-tts-test-banner/, "Test connection must use a styled result banner");
assert.match(cssSource, /\.ops-tts-test-banner/, "CSS must style TTS test connection banner");
assert.doesNotMatch(componentSource, /ops-tts-test-banner is-inline/, "Success notis must not use narrow pill chrome");
assert.doesNotMatch(cssSource, /\.ops-tts-test-banner\.is-inline/, "CSS must drop inline pill banner styles");
assert.match(componentSource, /ops-tts-test-banner__chip/, "Success notis must show a short chip");
assert.match(
  componentSource,
  /testResult\.ok && testSuccess[\s\S]*?ops-tts-test-banner__message[\s\S]*?testSuccess\.message[\s\S]*?ops-tts-test-banner__hint[\s\S]*?(?:testOkHint|testOkDraftHint)/,
  "Check-passed success must show message + next-step hint in the full-width banner"
);
assert.match(
  componentSource,
  /already_satisfied[\s\S]*?ops-tts-test-banner__message[\s\S]*?installAlreadyHint[\s\S]*?ops-tts-test-banner__hint[\s\S]*?installSuccessHint/,
  "Already-installed success must show message + next-step hint in the full-width banner"
);
assert.match(enSource, /"installSuccessHint"/, "TTS i18n must include install success next-step hint");
assert.match(cssSource, /\.ops-tts-test-banner[\s\S]*?width:\s*100%/, "Success banners must stretch full width");
assert.match(
  componentSource,
  /async function onTest\([\s\S]*?setTestResult\(\{\s*ok:\s*false/,
  "Test API failures must feed the test banner, not only bare page error text"
);
assert.match(
  componentSource,
  /ops-tts-test-banner__dismiss[\s\S]*?setTestResult\(null\)/,
  "Test banner must be dismissible"
);
{
  const applyStart = componentSource.indexOf("function applyResponse(");
  const applyEnd = componentSource.indexOf("async function loadList(", applyStart);
  const applyChunk = componentSource.slice(applyStart, applyEnd > applyStart ? applyEnd : applyStart + 2000);
  assert.match(applyChunk, /setRuntime\(data\.runtime/, "Edit hydrate must keep runtime for Ready / Last install");
  assert.match(applyChunk, /setTestResult\(null\)/, "Edit hydrate must clear the Check passed banner");
  assert.match(applyChunk, /setInstallResult\(null\)/, "Edit hydrate must clear the Already installed banner");
  assert.doesNotMatch(
    applyChunk,
    /last_probe[\s\S]*?setTestResult\(\{/,
    "Edit must not revive Check passed from last_probe"
  );
  assert.doesNotMatch(
    applyChunk,
    /last_install[\s\S]*?setInstallResult\(\{/,
    "Edit must not revive Already installed from last_install"
  );
}
assert.match(enSource, /"customProviderInvalid"/, "EN must define invalid custom slug copy");
assert.match(enSource, /"customProviderInvalidHint"/, "EN must define invalid custom slug hint");
assert.match(viSource, /"customProviderInvalidHint"/, "VI must define invalid custom slug hint");
assert.match(
  enSource,
  /"customProviderInvalid"\s*:\s*"Custom slug/,
  "Invalid slug copy must say Custom slug"
);
assert.match(
  componentSource,
  /setTestResult\(\{\s*ok:\s*false[\s\S]*?customProviderInvalid/,
  "Invalid custom slug must use the fail banner, not only bare inline-error"
);
assert.match(
  componentSource,
  /testResult\.detail === t\("opsTtsAi\.customProviderInvalid"\)/,
  "Fail banner must show customProviderInvalidHint for invalid slug"
);
assert.match(componentSource, /testNeedProvider/, "Missing provider must surface a clear Test failure");
assert.match(enSource, /"testNeedProvider"/, "EN must define missing provider Test copy");
assert.match(enSource, /"Probe connection"/, "EN Test action must say Probe connection");
{
  const onTestStart = componentSource.indexOf("async function onTest(");
  const onTestEnd = componentSource.indexOf("function onKindChange(", onTestStart);
  const onTestChunk = componentSource.slice(onTestStart, onTestEnd > onTestStart ? onTestEnd : onTestStart + 2500);
  assert.match(onTestChunk, /testNeedApiKey/, "Cloud Test must fail early without API key");
  assert.match(onTestChunk, /testNeedBaseUrl/, "HTTP Test must fail early without Base URL");
  assert.match(onTestChunk, /meta\.apiKeySet/, "Cloud Test must accept a saved API key without re-entry");
}
assert.match(enSource, /"testNeedApiKey"/, "EN must define missing API key Test copy");
assert.match(enSource, /"testNeedBaseUrl"/, "EN must define missing Base URL Test copy");
assert.match(viSource, /"testNeedApiKey"/, "VI must define missing API key Test copy");
assert.match(viSource, /"testNeedBaseUrl"/, "VI must define missing Base URL Test copy");
{
  const slugStart = componentSource.indexOf("function onCustomSlugInput(");
  const slugEnd = componentSource.indexOf("async function copyInstallCommand(", slugStart);
  const slugChunk = componentSource.slice(slugStart, slugEnd > slugStart ? slugEnd : slugStart + 1500);
  assert.match(slugChunk, /providerChoice:\s*"custom"/, "Custom slug typing must stay on Local custom");
  assert.doesNotMatch(slugChunk, /setKind\(/, "Custom slug typing must not change kind tab");
}
assert.match(
  componentSource,
  /\(isCloud \|\| isHttp\) \? \([\s\S]*?sectionCredentials/,
  "Cloud/HTTP must show credentials shell even when provider fields are empty"
);
assert.doesNotMatch(
  componentSource,
  /\(isCloud \|\| isHttp\) && \(fieldCaps\.base_url \|\| fieldCaps\.api_key\)/,
  "Cloud/HTTP credentials must not hide behind empty fieldCaps"
);
assert.match(
  componentSource,
  /activeProvider\.trim\(\) \? activeProvider : t\("opsTtsAi\.providerUnset"\)/,
  "Status chip must not render an empty provider pill — show unset label instead"
);
assert.match(enSource, /"providerUnset"/, "EN must define unset provider status chip label");
assert.match(componentSource, /formatTtsProbeSuccess/, "Success banner must humanize TTS probe results");
assert.match(componentSource, /testOkDraftHint/, "Unsaved New draft must explain probe is not a finished setup");
assert.doesNotMatch(componentSource, /ops-tts-status-pill|is-mini/, "Success notis must not use status-pill / mini chrome");
assert.doesNotMatch(
  componentSource,
  /ops-connection-status is-ok[\s\S]{0,80}?opsTtsAi\.(saved|profileDeleted)/,
  "Save/delete must not show Saved or Setup deleted toolbar chips"
);
assert.doesNotMatch(
  componentSource,
  /ops-ai-toolbar[\s\S]{0,1200}?testResult\?\.ok[\s\S]{0,400}?ops-connection-status/,
  "Toolbar must not show a duplicate Check passed chip next to Back/Test/Save"
);
assert.doesNotMatch(
  componentSource,
  /ops-connection-status[^>]*>[\s\S]{0,80}?opsTtsAi\.testOk/,
  "ops-connection-status chip must not render Check passed"
);
assert.doesNotMatch(
  componentSource,
  /testResult\.ok \? \([\s\S]*?formatConnectionTestSummary\(testResult/,
  "Success banner must not dump Ready · provider — raw probe jargon in one line"
);
assert.match(enSource, /"testOkDraftHint"/, "TTS i18n must include draft test hint");
assert.match(enSource, /"testProbeAutoVieneu"/, "TTS i18n must humanize auto→vieneu probe");
{
  const onTestStart = componentSource.indexOf("async function onTest(");
  const onTestEnd = componentSource.indexOf("async function", onTestStart + 1);
  const onTestChunk = componentSource.slice(onTestStart, onTestEnd > onTestStart ? onTestEnd : undefined);
  assert.doesNotMatch(
    onTestChunk,
    /setError\(err instanceof Error \? err\.message : t\("opsTtsAi\.testError"\)\)/,
    "onTest catch must not dump API failures into bare inline-error"
  );
}
assert.match(enSource, /"testErrorHint"/, "TTS i18n must include test error hint");
{
  const apiFail = formatProviderError("Failed to test TTS AI connection: 500", {
    unauthorized: "Invalid API key",
    forbidden: "Access denied",
    notFound: "Endpoint not found",
    rateLimited: "Rate limited",
    failed: "Connection check failed",
    checkKey: "Check the API key and try again.",
    checkForbidden: "The provider rejected this request. Check Base URL, key permissions, or a gateway/firewall block.",
    checkEndpoint: "Check Base URL and provider, then try again."
  });
  assert.equal(apiFail.httpStatus, 500);
  assert.equal(apiFail.title, "Connection check failed");
  assert.doesNotMatch(apiFail.message, /Failed to test TTS AI connection: 500/);
}
{
  const autoVieneu = formatTtsProbeSuccess(
    { ok: true, provider: "auto", detail: "auto → vieneu available" },
    {
      passed: "Check passed",
      autoVieneu: "System auto found VieNeu on this machine.",
      autoEdge: "System auto found edge-tts on this machine.",
      generic: "Provider probe succeeded."
    }
  );
  assert.equal(autoVieneu.title, "Check passed");
  assert.equal(autoVieneu.message, "System auto found VieNeu on this machine.");
  assert.equal(autoVieneu.provider, "auto → vieneu");
  assert.doesNotMatch(autoVieneu.message, /auto →/);
}
assert.match(catalogSource, /TTS_PROVIDERS_BY_KIND/, "Catalog must define provider kinds");
assert.match(catalogSource, /"custom"/, "Catalog must include custom local provider");
assert.match(catalogSource, /pip install vieneu/, "Catalog must include VieNeu install recipe");
assert.match(catalogSource, /pip install edge-tts/, "Catalog must include edge install recipe");
assert.match(
  cssSource,
  /\.ops-page--settings\s*\{[^}]*padding:\s*1rem var\(--app-content-inset-x\) 1\.35rem/,
  "Settings pages must use the shared app content inset"
);
assert.match(cssSource, /\.ops-tts-section--install/, "CSS must style install section");
assert.match(cssSource, /\.ops-tts-install-log/, "CSS must style install log");
assert.match(cssSource, /\.ops-tts-chip\.is-warn/, "CSS must style warn ready chip");
assert.match(apiSource, /\/ops\/tts-ai/, "API helper must hit /ops/tts-ai");
assert.match(apiSource, /\/ops\/tts-ai\/install/, "API helper must hit install endpoint");
assert.match(apiSource, /\/ops\/tts-ai\/install\/status/, "API helper must poll install status");
assert.match(apiSource, /fetchTtsAiInstallStatus/, "API helper must export install status poll");
assert.match(apiSource, /status\?:/, "Install response type must include async status");
assert.match(navSource, /nav\.ttsSettings/, "Nav must expose TTS settings");

const en = JSON.parse(enSource) as {
  opsTtsAi: {
    kindLocal: string;
    sectionInstall: string;
    installCommand: string;
    install: string;
    providerCustom: string;
    customProviderSlug: string;
    readyReady: string;
    readyInstalled: string;
    readyNotInstalled: string;
    readyUnchecked: string;
    sectionProfiles: string;
    profileNew: string;
    profileRename: string;
    profileRenameHint: string;
    profileDelete: string;
    profileEdit: string;
    profileActiveCol: string;
    profileSetupsCount: string;
    profileEmpty: string;
  };
  nav: { ttsSettings: string };
};
assert.equal(en.opsTtsAi.kindLocal, "Local / SDK");
assert.ok(en.opsTtsAi.sectionInstall.length > 0);
assert.ok(en.opsTtsAi.installCommand.length > 0);
assert.ok(en.opsTtsAi.install.length > 0);
assert.ok(en.opsTtsAi.providerCustom.length > 0);
assert.ok(en.opsTtsAi.customProviderSlug.length > 0);
assert.equal(en.opsTtsAi.readyReady, "Ready");
assert.ok(en.opsTtsAi.readyInstalled.length > 0);
assert.ok(en.opsTtsAi.readyNotInstalled.length > 0);
assert.ok(en.opsTtsAi.readyUnchecked.length > 0);
assert.equal(en.opsTtsAi.sectionProfiles, "Saved setups");
assert.equal(en.opsTtsAi.profileNew, "New");
assert.ok(en.opsTtsAi.profileRename.length > 0);
assert.match(en.opsTtsAi.profileRenameHint, /click|name/i);
assert.ok(en.opsTtsAi.profileDelete.length > 0);
assert.ok(en.opsTtsAi.profileEdit.length > 0);
assert.equal(en.opsTtsAi.profileActiveCol, "Active");
assert.match(en.opsTtsAi.profileSetupsCount, /setup/i);
assert.ok(en.opsTtsAi.profileEmpty.length > 0);
assert.ok(en.nav.ttsSettings.length > 0);

assert.match(componentSource, /deriveTtsInstallFromRepoUrl/, "Install form must derive pip git+ from Repo URL");
assert.match(componentSource, /function applyRepoUrl/, "Repo URL input must auto-fill install fields");
assert.match(componentSource, /repoUrlHint/, "Repo URL must explain auto-fill");
assert.match(componentSource, /extraRequirementHint/, "Extra requirements must be marked optional note");
assert.match(
  componentSource,
  /async function onInstall\([\s\S]*?derived\.installCommand/,
  "Install must prefer repo-derived git+ over stale PyPI package commands"
);
assert.match(
  componentSource,
  /async function onInstall\([\s\S]*?setInstallResult\(\{\s*ok:\s*false/,
  "Install API failures must show in the install result banner, not only top-of-page error"
);
assert.match(componentSource, /installingHint/, "Install must show in-progress feedback near the Install button");
assert.match(componentSource, /pollInstallUntilDone/, "Install must poll until succeeded or failed");
assert.match(componentSource, /fetchTtsAiInstallStatus/, "Install poll must use status endpoint helper");
assert.match(componentSource, /result\.status === "running"/, "Install must treat POST running as async job");
assert.match(componentSource, /installPollTimeout/, "Install poll must surface a timeout message");
assert.match(enSource, /"installPollTimeout"/, "en.json must define install poll timeout copy");
assert.match(viSource, /"installPollTimeout"/, "vi.json must define install poll timeout copy");
assert.doesNotMatch(
  componentSource,
  /async function onInstall\([\s\S]*?setError\(err instanceof Error \? err\.message : t\("opsTtsAi\.installError"\)\)/,
  "onInstall catch must not dump failures into bare page-top inline-error only"
);
assert.match(componentSource, /forceReinstall|force_reinstall/, "Install must support force reinstall");
assert.match(componentSource, /reinstallUpgrade/, "UI must expose Reinstall / Upgrade action");
assert.match(componentSource, /useInstalled/, "UI must label use-installed when package already present");
assert.match(componentSource, /getTtsFieldCapabilities/, "Form must resolve adaptive field capabilities");
assert.match(componentSource, /fieldCaps\.model/, "Model field must follow capabilities");
assert.match(componentSource, /resolveProviderSlugFromInstall/, "Install success must hydrate provider from package");
assert.match(
  componentSource,
  /function applyRepoUrl\([\s\S]*?packageName:\s*derived\.packageName/,
  "Repo URL must sync package name from the repo (not keep stale edge-tts)"
);
assert.match(apiSource, /force_reinstall/, "API client must send force_reinstall");
assert.match(enSource, /"useInstalled"/, "en.json must define use-installed label");
assert.match(enSource, /"reinstallUpgrade"/, "en.json must define reinstall upgrade label");
{
  const derived = deriveTtsInstallFromRepoUrl("https://github.com/debpalash/OmniVoice-Studio.git");
  assert.ok(derived);
  assert.equal(derived.packageName, "OmniVoice-Studio");
  assert.equal(
    derived.installCommand,
    "pip install git+https://github.com/debpalash/OmniVoice-Studio.git"
  );
}
assert.equal(resolveTtsProviderKind("vieneu"), "local");
assert.equal(resolveTtsProviderKind("google"), "cloud");
assert.equal(resolveTtsProviderKind("openai_compatible"), "http");
assert.equal(resolveTtsProviderKind("auto"), "system");
assert.equal(showsTtsApiKey("google"), true);
assert.equal(showsTtsApiKey("edge"), false);
assert.equal(showsTtsBaseUrl("openai_compatible"), true);
assert.equal(showsTtsBaseUrl("vieneu"), false);
assert.equal(showsTtsBaseUrl("vieneu", "remote"), true);
assert.equal(showsTtsBaseUrl("vieneu", "auto"), false);
assert.equal(showsTtsLocalBackend("vieneu"), true);
assert.equal(getLocalInstallRecipe("vieneu")?.installCommand, "pip install vieneu");
assert.equal(getLocalInstallRecipe("edge")?.extraRequirement.includes("ffmpeg"), true);

console.log("ops-tts-ai tests passed");
