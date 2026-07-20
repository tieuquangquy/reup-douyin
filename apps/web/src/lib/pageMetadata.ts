import type { Metadata } from "next";

export const SITE_NAME = "Reup Douyin";

const DEFAULT_DESCRIPTION =
  "Local-first operator studio for Douyin capture, review, production, export, and manual publish workflows.";

type PageMetadataInput = {
  title: string;
  description: string;
  noIndex?: boolean;
};

export function createPageMetadata({ title, description, noIndex = false }: PageMetadataInput): Metadata {
  const fullTitle = `${title} | ${SITE_NAME}`;

  return {
    title,
    description,
    applicationName: SITE_NAME,
    ...(noIndex ? { robots: { index: false, follow: false } } : {}),
    openGraph: {
      title: fullTitle,
      description,
      siteName: SITE_NAME,
      type: "website"
    },
    twitter: {
      card: "summary",
      title: fullTitle,
      description
    }
  };
}

export function createDetailPageMetadata(title: string, description: string): Metadata {
  return createPageMetadata({ title, description });
}

export function shortResourceId(value: string, length = 8): string {
  const trimmed = value.trim();
  if (trimmed.length <= length) return trimmed;
  return `${trimmed.slice(0, length)}…`;
}

export const pageMetadata = {
  home: createPageMetadata({
    title: "Operator Home",
    description: "Start daily operator work across intake, review, production, and publishing."
  }),
  signIn: createPageMetadata({
    title: "Sign In",
    description: "Sign in to your local Reup Douyin operator workspace.",
    noIndex: true
  }),
  register: createPageMetadata({
    title: "Create Account",
    description: "Create a local operator account for Reup Douyin.",
    noIndex: true
  }),
  intake: createPageMetadata({
    title: "Source Intake",
    description: "Start crawls, monitor intake sessions, and route captured Douyin work into review."
  }),
  intakeProfiles: createPageMetadata({
    title: "Source Profiles",
    description: "Browse and manage Douyin source profiles used by intake workflows."
  }),
  intakeCrawlSessions: createPageMetadata({
    title: "Crawl Sessions",
    description: "Inspect crawl session history and intake run context."
  }),
  reviewBoard: createPageMetadata({
    title: "Review Board",
    description: "Triage shortlisted clips, compare finalists, and approve reup candidates."
  }),
  reupQueue: createPageMetadata({
    title: "Reup Queue",
    description: "Prepare approved clips for export packages and manual publish handoffs."
  }),
  captureInbox: createPageMetadata({
    title: "Capture Inbox",
    description: "Stage Douyin captures, fix incomplete items, and promote ready work to Review Board."
  }),
  douyinAccounts: createPageMetadata({
    title: "Douyin Accounts",
    description: "Manage Douyin account connections used by capture and intake workflows."
  }),
  douyinExtensionSetup: createPageMetadata({
    title: "Douyin Extension Setup",
    description: "Install and verify the Douyin browser extension for local capture workflows."
  }),
  douyinExtensionManager: createPageMetadata({
    title: "Douyin Extension Manager",
    description: "Monitor extension health, connection status, and capture tooling."
  }),
  downloads: createPageMetadata({
    title: "Downloads",
    description: "Track downloaded source media and production download context."
  }),
  transcriptEditor: createPageMetadata({
    title: "Transcript Editor",
    description: "Edit transcripts and localization checkpoints for a selected source video."
  }),
  finalReview: createPageMetadata({
    title: "Final Review",
    description: "Review rendered output and production readiness before publishing."
  }),
  publishDrafts: createPageMetadata({
    title: "Publish Drafts",
    description: "Browse publish-ready drafts and continue manual publishing preparation."
  }),
  publishDraft: createPageMetadata({
    title: "Publish Draft",
    description: "Inspect a publish draft, caption, media summary, and scheduling skeleton."
  }),
  exportPackages: createPageMetadata({
    title: "Export Packages",
    description: "Inspect durable export packages created from Reup Queue items."
  }),
  exportPackage: createPageMetadata({
    title: "Export Package",
    description: "Review export package contents, metadata, and downstream handoff readiness."
  }),
  publishHandoffs: createPageMetadata({
    title: "Publish Handoffs",
    description: "Inspect manual publish handoff payloads created from export packages."
  }),
  publishHandoff: createPageMetadata({
    title: "Publish Handoff",
    description: "Review handoff payload details for manual operator publishing."
  }),
  optimization: createPageMetadata({
    title: "Optimization",
    description: "Review outcome hints, routing guidance, and operator optimization signals."
  }),
  opsHome: createPageMetadata({
    title: "Ops Console",
    description: "Operate the local system health, jobs, publish controls, and operational tooling."
  }),
  opsHealth: createPageMetadata({
    title: "System Health",
    description: "Monitor API, worker, storage, and dependency health for the local stack."
  }),
  opsJobs: createPageMetadata({
    title: "Job Monitor",
    description: "Track background jobs, retries, failures, and execution state."
  }),
  opsUsers: createPageMetadata({
    title: "Users",
    description: "Invite operators, manage workspace roles, and disable access."
  }),
  opsAssets: createPageMetadata({
    title: "Asset State",
    description: "Inspect durable asset state across intake, production, and publishing."
  }),
  opsAccounts: createPageMetadata({
    title: "Accounts",
    description: "Manage publish accounts and operator routing context."
  }),
  opsRisk: createPageMetadata({
    title: "Risk Gates",
    description: "Review risk gates, publish safeguards, and operator escalation rules."
  }),
  opsRoutingRules: createPageMetadata({
    title: "Routing Rules",
    description: "Configure how approved work routes across accounts and publish surfaces."
  }),
  opsReconciliation: createPageMetadata({
    title: "Reconciliation",
    description: "Reconcile publish attempts, queue state, and downstream delivery signals."
  }),
  opsPublishAttempts: createPageMetadata({
    title: "Publish Attempts",
    description: "Audit publish attempts, failures, and retry history."
  }),
  opsPublishHealth: createPageMetadata({
    title: "Publish Health",
    description: "Monitor publish pipeline health, blockers, and operator attention signals."
  }),
  opsPublishControl: createPageMetadata({
    title: "Publish Control",
    description: "Control publish queues, operator actions, and manual intervention points."
  }),
  opsOptimization: createPageMetadata({
    title: "Ops Optimization",
    description: "Review operational optimization signals for routing and scheduling decisions."
  }),
  opsTools: createPageMetadata({
    title: "Ops Tools",
    description: "Access operator utilities, diagnostics, and supporting operational tools."
  }),
  opsTranslationPrompt: createPageMetadata({
    title: "Translation settings",
    description: "Edit the workspace Chinese→Vietnamese dialogue translation system prompt stored in the database."
  }),
  opsTranslationAi: createPageMetadata({
    title: "Translation settings",
    description: "Configure the workspace translation LLM provider, model, API key, and base URL."
  }),
  opsCaptionPrompt: createPageMetadata({
    title: "Caption AI settings",
    description: "Edit the hard-sub caption ZH→VI system prompt (separate from dialogue Translation prompt)."
  }),
  opsCaptionAi: createPageMetadata({
    title: "Caption AI settings",
    description: "Configure the LLM for hard-sub / OCR caption translation (separate from dialogue Translation settings)."
  }),
  opsTtsAi: createPageMetadata({
    title: "TTS settings",
    description: "Configure Vietnamese TTS providers (edge, VieNeu, cloud, HTTP) for Generate TTS jobs."
  }),
  pipelineDashboard: createPageMetadata({
    title: "Pipeline Dashboard",
    description: "Track intake, review, production, export, and publish pipeline health."
  })
} as const satisfies Record<string, Metadata>;

export const rootMetadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000"),
  title: {
    default: SITE_NAME,
    template: `%s | ${SITE_NAME}`
  },
  description: DEFAULT_DESCRIPTION,
  applicationName: SITE_NAME,
  icons: {
    icon: [{ url: "/brand/logo-loop-r.svg", type: "image/svg+xml" }, { url: "/brand/logo-loop-r.png", sizes: "512x512", type: "image/png" }],
    apple: [{ url: "/brand/logo-loop-r.png", sizes: "180x180", type: "image/png" }]
  },
  openGraph: {
    title: SITE_NAME,
    description: DEFAULT_DESCRIPTION,
    siteName: SITE_NAME,
    type: "website",
    images: [{ url: "/brand/logo-loop-r.png", width: 512, height: 512, alt: SITE_NAME }]
  },
  twitter: {
    card: "summary",
    title: SITE_NAME,
    description: DEFAULT_DESCRIPTION,
    images: ["/brand/logo-loop-r.png"]
  }
};
