import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "../src/app");

const staticPages = [
  ["page.tsx", "../../lib/pageMetadata", "pageMetadata.home"],
  ["intake/page.tsx", "../../lib/pageMetadata", "pageMetadata.intake"],
  ["intake/profiles/page.tsx", "../../../lib/pageMetadata", "pageMetadata.intakeProfiles"],
  ["intake/crawl-sessions/page.tsx", "../../../lib/pageMetadata", "pageMetadata.intakeCrawlSessions"],
  ["selection/review-board/page.tsx", "../../../lib/pageMetadata", "pageMetadata.reviewBoard"],
  ["selection/reup-queue/page.tsx", "../../../lib/pageMetadata", "pageMetadata.reupQueue"],
  ["ops/extensions/douyin/capture-inbox/page.tsx", "../../../../../lib/pageMetadata", "pageMetadata.captureInbox"],
  ["accounts/douyin/page.tsx", "../../../lib/pageMetadata", "pageMetadata.douyinAccounts"],
  ["setup/douyin-extension/page.tsx", "../../../lib/pageMetadata", "pageMetadata.douyinExtensionSetup"],
  ["ops/extensions/douyin/page.tsx", "../../../../lib/pageMetadata", "pageMetadata.douyinExtensionManager"],
  ["production/downloads/page.tsx", "../../../lib/pageMetadata", "pageMetadata.downloads"],
  ["publishing/drafts/page.tsx", "../../../lib/pageMetadata", "pageMetadata.publishDrafts"],
  ["publishing/export-packages/page.tsx", "../../../lib/pageMetadata", "pageMetadata.exportPackages"],
  ["publishing/publish-handoffs/page.tsx", "../../../lib/pageMetadata", "pageMetadata.publishHandoffs"],
  ["optimization/page.tsx", "../../lib/pageMetadata", "pageMetadata.optimization"],
  ["ops/page.tsx", "../../lib/pageMetadata", "pageMetadata.opsHome"],
  ["ops/health/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsHealth"],
  ["ops/jobs/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsJobs"],
  ["ops/assets/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsAssets"],
  ["ops/accounts/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsAccounts"],
  ["ops/risk/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsRisk"],
  ["ops/routing-rules/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsRoutingRules"],
  ["ops/reconciliation/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsReconciliation"],
  ["ops/publish-attempts/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsPublishAttempts"],
  ["ops/publish-health/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsPublishHealth"],
  ["ops/publish-control/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsPublishControl"],
  ["ops/optimization/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsOptimization"],
  ["ops/tools/page.tsx", "../../../lib/pageMetadata", "pageMetadata.opsTools"],
  ["ops/pipeline/page.tsx", "../../../lib/pageMetadata", "pageMetadata.pipelineDashboard"]
];

for (const [rel, importPath, exportName] of staticPages) {
  const file = path.join(root, rel);
  let src = fs.readFileSync(file, "utf8");
  if (src.includes("export const metadata")) continue;
  const importLine = `import { pageMetadata } from "${importPath}";\n\nexport const metadata = ${exportName};\n\n`;
  fs.writeFileSync(file, importLine + src);
}

const dynamicTemplates = [
  ["production/final-review/[sourceVideoId]/page.tsx", "../../../../lib/pageMetadata", "finalReview", "sourceVideoId"],
  ["production/transcript-editor/[sourceVideoId]/page.tsx", "../../../../lib/pageMetadata", "transcriptEditor", "sourceVideoId"],
  ["publishing/drafts/[draftId]/page.tsx", "../../../../lib/pageMetadata", "publishDraft", "draftId"],
  ["publishing/export-packages/[packageId]/page.tsx", "../../../../lib/pageMetadata", "exportPackage", "packageId"],
  ["publishing/publish-handoffs/[handoffId]/page.tsx", "../../../../lib/pageMetadata", "publishHandoff", "handoffId"],
  ["source-videos/[id]/publish/page.tsx", "../../../../lib/pageMetadata", "publishDraft", "id"]
];

for (const [rel, importPath, key, param] of dynamicTemplates) {
  const file = path.join(root, rel);
  let src = fs.readFileSync(file, "utf8");
  if (src.includes("generateMetadata")) continue;
  const block = `import type { Metadata } from "next";\nimport { createDetailPageMetadata, pageMetadata, shortResourceId } from "${importPath}";\n\nexport async function generateMetadata({ params }: { params: Promise<{ ${param}: string }> }): Promise<Metadata> {\n  const { ${param} } = await params;\n  const base = pageMetadata.${key};\n  const title = typeof base.title === "string" ? base.title : "${key}";\n  return createDetailPageMetadata(\`\${title} \${shortResourceId(${param})}\`, base.description ?? "");\n}\n\n`;
  fs.writeFileSync(file, block + src);
}

fs.mkdirSync(path.join(root, "auth/login"), { recursive: true });
fs.mkdirSync(path.join(root, "auth/register"), { recursive: true });
fs.writeFileSync(
  path.join(root, "auth/login/layout.tsx"),
  `import { pageMetadata } from "../../../lib/pageMetadata";\n\nexport const metadata = pageMetadata.signIn;\n\nexport default function LoginLayout({ children }: { children: React.ReactNode }) {\n  return children;\n}\n`
);
fs.writeFileSync(
  path.join(root, "auth/register/layout.tsx"),
  `import { pageMetadata } from "../../../lib/pageMetadata";\n\nexport const metadata = pageMetadata.register;\n\nexport default function RegisterLayout({ children }: { children: React.ReactNode }) {\n  return children;\n}\n`
);

console.log("patched page metadata");
