export type NavSurface = "operator" | "ops";

export type NavIconName =
  | "home"
  | "pipeline"
  | "inbox"
  | "review"
  | "queue"
  | "output"
  | "transcript"
  | "final"
  | "draft"
  | "package"
  | "handoff"
  | "extension"
  | "dashboard"
  | "health"
  | "jobs"
  | "users"
  | "accounts"
  | "translation"
  | "caption"
  | "voice"
  | "settings";

export type NavItem = {
  /** i18n key, e.g. "nav.home" */
  label: string;
  href: string;
  /** i18n key, e.g. "nav.homeDesc" */
  description: string;
  icon: NavIconName;
  status?: "available" | "placeholder" | "context";
  activePatterns?: string[];
  external?: boolean;
  sourceVideoTarget?: "transcript-editor" | "final-review";
  sourceVideoFallbackLabel?: string;
};

export type NavSection = {
  /** i18n key, e.g. "nav.sectionWork" */
  title: string;
  items: NavItem[];
};

export type BreadcrumbItem = {
  label: string;
  href?: string;
};

/** Operator Studio: day-to-day Collect → Review → Queue → Edit → Final → Publish. */
export const operatorNavSections: NavSection[] = [
  {
    title: "nav.sectionHome",
    items: [
      {
        label: "nav.home",
        href: "/",
        icon: "home",
        description: "nav.homeDesc",
        status: "available"
      },
      {
        label: "nav.pipelineDashboard",
        href: "/ops/pipeline",
        icon: "pipeline",
        description: "nav.pipelineDashboardDesc",
        status: "available",
        activePatterns: ["/ops/pipeline"]
      }
    ]
  },
  {
    title: "nav.sectionWork",
    items: [
      {
        label: "nav.captureInbox",
        href: "/selection/capture-inbox",
        icon: "inbox",
        description: "nav.captureInboxDesc",
        status: "available",
        activePatterns: ["/selection/capture-inbox", "/ops/extensions/douyin/capture-inbox"]
      },
      {
        label: "nav.reviewBoard",
        href: "/selection/review-board",
        icon: "review",
        description: "nav.reviewBoardDesc",
        status: "available",
        activePatterns: ["/selection/review-board", "/selection/candidates", "/review-board"]
      },
      {
        label: "nav.reupQueue",
        href: "/selection/reup-queue",
        icon: "queue",
        description: "nav.reupQueueDesc",
        status: "available",
        activePatterns: ["/selection/reup-queue"]
      }
    ]
  },
  {
    title: "nav.sectionProduction",
    items: [
      {
        label: "nav.outputReview",
        href: "/production/output-review",
        icon: "output",
        description: "nav.outputReviewDesc",
        status: "available",
        activePatterns: ["/production/output-review"]
      },
      {
        label: "nav.transcriptEditor",
        href: "/selection/review-board",
        icon: "transcript",
        description: "nav.transcriptEditorDesc",
        status: "context",
        sourceVideoTarget: "transcript-editor",
        sourceVideoFallbackLabel: "nav.selectVideo",
        activePatterns: [
          "/production/transcript-editor/*",
          "/source-videos/*/transcript-editor"
        ]
      },
      {
        label: "nav.finalReview",
        href: "/publishing/drafts",
        icon: "final",
        description: "nav.finalReviewDesc",
        status: "context",
        sourceVideoTarget: "final-review",
        sourceVideoFallbackLabel: "nav.selectOutput",
        activePatterns: [
          "/production/final-review/*",
          "/source-videos/*/final-review"
        ]
      }
    ]
  },
  {
    title: "nav.sectionPublishing",
    items: [
      {
        label: "nav.publishDrafts",
        href: "/publishing/drafts",
        icon: "draft",
        description: "nav.publishDraftsDesc",
        status: "available",
        activePatterns: ["/publishing/drafts", "/publishing/drafts/*", "/source-videos/*/publish"]
      },
      {
        label: "nav.accounts",
        href: "/publishing/accounts",
        icon: "accounts",
        description: "nav.accountsDesc",
        status: "available",
        activePatterns: ["/publishing/accounts"]
      },
      {
        label: "nav.publications",
        href: "/publishing/publications",
        icon: "draft",
        description: "nav.publicationsDesc",
        status: "available",
        activePatterns: ["/publishing/publications"]
      },
      {
        label: "nav.exportPackages",
        href: "/publishing/export-packages",
        icon: "package",
        description: "nav.exportPackagesDesc",
        status: "available",
        activePatterns: ["/publishing/export-packages", "/publishing/export-packages/*"]
      },
      {
        label: "nav.publishHandoffs",
        href: "/publishing/publish-handoffs",
        icon: "handoff",
        description: "nav.publishHandoffsDesc",
        status: "available",
        activePatterns: ["/publishing/publish-handoffs", "/publishing/publish-handoffs/*"]
      }
    ]
  },
  {
    title: "nav.sectionPublishingSettings",
    items: [
      {
        label: "nav.publishingSettings",
        href: "/publishing/settings/content-intelligence",
        icon: "settings",
        description: "nav.publishingSettingsDesc",
        status: "available",
        activePatterns: ["/publishing/settings/content-intelligence", "/publishing/settings/affiliate-catalog", "/publishing/settings/affiliate-comments"]
      }
    ]
  },
  {
    title: "nav.sectionSetup",
    items: [
      {
        label: "nav.douyinExtensionSetup",
        href: "/setup/douyin-extension",
        icon: "extension",
        description: "nav.douyinExtensionSetupDesc",
        status: "available",
        activePatterns: ["/setup/douyin-extension"]
      }
    ]
  }
];

/** Ops Console: AI settings + monitor (not day-to-day collect). */
export const opsNavSections: NavSection[] = [
  {
    title: "nav.sectionMonitor",
    items: [
      {
        label: "nav.opsHome",
        href: "/ops",
        icon: "dashboard",
        description: "nav.opsHomeDesc",
        status: "available"
      },
      {
        label: "nav.systemHealth",
        href: "/ops/health",
        icon: "health",
        description: "nav.systemHealthDesc",
        status: "available"
      },
      {
        label: "nav.jobMonitor",
        href: "/ops/jobs",
        icon: "jobs",
        description: "nav.jobMonitorDesc",
        status: "available"
      },
      {
        label: "nav.users",
        href: "/ops/users",
        icon: "users",
        description: "nav.usersDesc",
        status: "available",
        activePatterns: ["/ops/users"]
      }
    ]
  },
  {
    title: "nav.sectionAiSettings",
    items: [
      {
        label: "nav.translationSettings",
        href: "/ops/translation-ai",
        icon: "translation",
        description: "nav.translationSettingsDesc",
        status: "available",
        activePatterns: ["/ops/translation-ai", "/ops/translation-prompt"]
      },
      {
        label: "nav.captionAiSettings",
        href: "/ops/caption-ai",
        icon: "caption",
        description: "nav.captionAiSettingsDesc",
        status: "available",
        activePatterns: ["/ops/caption-ai", "/ops/caption-prompt"]
      },
      {
        label: "nav.ttsSettings",
        href: "/ops/tts-ai",
        icon: "voice",
        description: "nav.ttsSettingsDesc",
        status: "available",
        activePatterns: ["/ops/tts-ai"]
      }
    ]
  }
];

const breadcrumbRules: Array<{ patterns: string[]; crumbs: BreadcrumbItem[] }> = [
  { patterns: ["/"], crumbs: [{ label: "nav.home" }] },
  {
    patterns: ["/selection/capture-inbox", "/ops/extensions/douyin/capture-inbox"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionWork", href: "/selection/capture-inbox" },
      { label: "nav.captureInbox" }
    ]
  },
  {
    patterns: ["/selection/review-board", "/selection/candidates", "/review-board"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionWork", href: "/selection/review-board" },
      { label: "nav.reviewBoard" }
    ]
  },
  {
    patterns: ["/selection/reup-queue"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionWork", href: "/selection/review-board" },
      { label: "nav.reupQueue" }
    ]
  },
  {
    patterns: ["/production/downloads"],
    crumbs: [{ label: "nav.home", href: "/" }, { label: "nav.sectionProduction" }, { label: "nav.downloads" }]
  },
  {
    patterns: ["/production/output-review"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionProduction", href: "/selection/review-board" },
      { label: "nav.outputReview" }
    ]
  },
  {
    patterns: ["/production/transcript-editor/*", "/source-videos/*/transcript-editor"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionProduction", href: "/selection/review-board" },
      { label: "nav.transcriptEditor" }
    ]
  },
  {
    patterns: ["/production/final-review/*", "/source-videos/*/final-review"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionProduction", href: "/publishing/drafts" },
      { label: "nav.finalReview" }
    ]
  },
  {
    patterns: ["/publishing/drafts"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/drafts" },
      { label: "nav.publishDrafts" }
    ]
  },
  {
    patterns: ["/publishing/drafts/*", "/source-videos/*/publish"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/drafts" },
      { label: "nav.publishDraft" }
    ]
  },
  {
    patterns: ["/publishing/publications"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/drafts" },
      { label: "nav.publications" }
    ]
  },
  {
    patterns: ["/publishing/settings/content-intelligence"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishingSettings", href: "/publishing/settings/content-intelligence" },
      { label: "nav.contentIntelligenceSettings" }
    ]
  },
  {
    patterns: ["/publishing/settings/affiliate-catalog"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishingSettings", href: "/publishing/settings/content-intelligence" },
      { label: "nav.affiliateCatalog" }
    ]
  },
  {
    patterns: ["/publishing/settings/affiliate-comments"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishingSettings", href: "/publishing/settings/content-intelligence" },
      { label: "nav.affiliateComments" }
    ]
  },
  {
    patterns: ["/publishing/accounts"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/drafts" },
      { label: "nav.accounts" }
    ]
  },
  {
    patterns: ["/publishing/export-packages"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/export-packages" },
      { label: "nav.exportPackages" }
    ]
  },
  {
    patterns: ["/publishing/export-packages/*"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/export-packages" },
      { label: "nav.exportPackage" }
    ]
  },
  {
    patterns: ["/publishing/publish-handoffs"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/publish-handoffs" },
      { label: "nav.publishHandoffs" }
    ]
  },
  {
    patterns: ["/publishing/publish-handoffs/*"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionPublishing", href: "/publishing/publish-handoffs" },
      { label: "nav.publishHandoff" }
    ]
  },
  {
    patterns: ["/setup/douyin-extension"],
    crumbs: [
      { label: "nav.home", href: "/" },
      { label: "nav.sectionSetup", href: "/setup/douyin-extension" },
      { label: "nav.douyinExtensionSetup" }
    ]
  },
  // Routes kept reachable but removed from sidebar
  { patterns: ["/intake", "/intake/*"], crumbs: [{ label: "nav.home", href: "/" }, { label: "nav.intake" }] },
  {
    patterns: ["/optimization"],
    crumbs: [{ label: "nav.home", href: "/" }, { label: "nav.optimization" }]
  },
  { patterns: ["/ops"], crumbs: [{ label: "nav.opsConsole" }] },
  {
    patterns: ["/ops/pipeline"],
    crumbs: [{ label: "nav.home", href: "/" }, { label: "nav.pipelineDashboard" }]
  },
  { patterns: ["/ops/health"], crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.systemHealth" }] },
  {
    patterns: ["/ops/jobs"],
    crumbs: [
      { label: "nav.opsConsole", href: "/ops" },
      { label: "nav.sectionMonitor", href: "/ops/jobs" },
      { label: "nav.jobMonitor" }
    ]
  },
  {
    patterns: ["/ops/users"],
    crumbs: [
      { label: "nav.opsConsole", href: "/ops" },
      { label: "nav.sectionMonitor", href: "/ops/users" },
      { label: "nav.users" }
    ]
  },
  {
    patterns: ["/ops/assets"],
    crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.assetState" }]
  },
  {
    patterns: ["/ops/publish-health", "/dashboard/publish-health", "/publishing/health"],
    crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.publishHealth" }]
  },
  {
    patterns: ["/ops/publish-control", "/publish-control"],
    crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.publishControl" }]
  },
  {
    patterns: ["/ops/publish-attempts"],
    crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.publishAttempts" }]
  },
  {
    patterns: ["/ops/reconciliation"],
    crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.reconciliation" }]
  },
  {
    patterns: ["/ops/routing-rules"],
    crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.routingRules" }]
  },
  { patterns: ["/ops/risk"], crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.riskGates" }] },
  { patterns: ["/ops/tools"], crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.tools" }] },
  {
    patterns: ["/ops/translation-ai", "/ops/translation-prompt"],
    crumbs: [
      { label: "nav.opsConsole", href: "/ops" },
      { label: "nav.sectionAiSettings", href: "/ops/translation-ai" },
      { label: "nav.translationSettings" }
    ]
  },
  {
    patterns: ["/ops/caption-ai", "/ops/caption-prompt"],
    crumbs: [
      { label: "nav.opsConsole", href: "/ops" },
      { label: "nav.sectionAiSettings", href: "/ops/caption-ai" },
      { label: "nav.captionAiSettings" }
    ]
  },
  {
    patterns: ["/ops/tts-ai"],
    crumbs: [
      { label: "nav.opsConsole", href: "/ops" },
      { label: "nav.sectionAiSettings", href: "/ops/tts-ai" },
      { label: "nav.ttsSettings" }
    ]
  },
  {
    patterns: ["/ops/optimization"],
    crumbs: [{ label: "nav.opsConsole", href: "/ops" }, { label: "nav.optimization" }]
  }
];

export function getSurfaceLabel(surface: NavSurface): string {
  return surface === "operator" ? "Operator Studio" : "Ops Console";
}

export function getSurfaceLabelKey(surface: NavSurface): string {
  return surface === "operator" ? "nav.operatorStudio" : "nav.opsConsole";
}

export function isNavItemActive(item: NavItem, activePath: string): boolean {
  const patterns = item.activePatterns ?? [item.href];
  return patterns.some((pattern) => matchPathPattern(pattern, activePath));
}

export function getBreadcrumbs(pathname: string): BreadcrumbItem[] {
  const rule = breadcrumbRules.find((item) => item.patterns.some((pattern) => matchPathPattern(pattern, pathname)));
  if (rule) return rule.crumbs;
  if (pathname.startsWith("/ops")) return [{ label: "nav.opsConsole", href: "/ops" }];
  return [{ label: "nav.home", href: "/" }];
}

export function extractSourceVideoIdFromPath(pathname: string): string | null {
  const sourceVideoMatch = pathname.match(/^\/source-videos\/([^/]+)\/(?:transcript-editor|final-review|publish)$/);
  if (sourceVideoMatch?.[1]) return decodeURIComponent(sourceVideoMatch[1]);

  const productionMatch = pathname.match(/^\/production\/(?:transcript-editor|final-review)\/([^/]+)$/);
  if (productionMatch?.[1]) return decodeURIComponent(productionMatch[1]);

  return null;
}

export function getSourceVideoNavHref(target: NonNullable<NavItem["sourceVideoTarget"]>, sourceVideoId: string): string {
  const id = encodeURIComponent(sourceVideoId);
  if (target === "transcript-editor") return `/production/transcript-editor/${id}`;
  return `/production/final-review/${id}`;
}

export function resolveNavItemHref(item: NavItem, sourceVideoId: string | null): string {
  if (item.sourceVideoTarget && sourceVideoId) {
    return getSourceVideoNavHref(item.sourceVideoTarget, sourceVideoId);
  }
  return item.href;
}

export function resolveNavItemStatusLabel(item: NavItem, sourceVideoId: string | null): string | null {
  if (item.sourceVideoTarget) {
    return sourceVideoId ? null : item.sourceVideoFallbackLabel ?? "nav.selectVideo";
  }
  if (item.status === "placeholder") return "common.planned";
  if (item.status === "context") return "common.context";
  return null;
}

function matchPathPattern(pattern: string, pathname: string): boolean {
  if (pattern === "/") return pathname === "/";
  if (pattern.endsWith("/*")) {
    const base = pattern.slice(0, -2);
    return pathname === base || pathname.startsWith(`${base}/`);
  }
  if (pattern.includes("*")) {
    const escaped = pattern
      .split("*")
      .map(escapeRegExp)
      .join("[^/]+");
    return new RegExp(`^${escaped}$`).test(pathname);
  }
  return pathname === pattern;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
