import type {
  BulkActionStatus,
  Candidate,
  CandidateDeleteResponse,
  CandidateFilters,
  CandidateListResponse,
  CandidateSummary,
  FilterPresetListResponse
} from "../types/review-board";
import type { TtsCreateResponse, TtsSummaryResponse } from "../types/tts";
import type { OcrCreateResponse, OcrSummaryResponse } from "../types/ocr";
import type {
  Job,
  JobListResponse,
  JobStatus,
  JobType
} from "../types/jobs";
import type {
  AudioAnalysisSummaryResponse,
  TranscriptListResponse,
  TranscriptSavePayload,
  TranslationDraftListResponse,
  TranslationPreset
} from "../types/transcript-editor";
import type {
  RenderCreateResponse,
  RenderOutput,
  SourceVideoAssetManifest
} from "../types/final-review";
import type {
  PublishDraft,
  PublishDraftListResponse,
  PlatformAccount,
  PlatformAccountListResponse,
  PublishHistoryResponse,
  PublishAttempt,
  PublishAttemptListResponse,
  PublishTarget,
  PublishTargetPlatform
} from "../types/publish-draft";
import type { OperatorRiskDecisionType, RiskFlag, RiskSummary, RiskTargetType } from "../types/risk";
import type { AnalyticsWindow, OperatorFeedbackPayload, PublishHealthDashboard } from "../types/analytics";
import type {
  AssignDraftPayload,
  BulkAssignPayload,
  PublishControlQueue,
  RoutingRecommendation,
  RoutingRuleListResponse
} from "../types/publish-control";
import type { OptimizationDashboard, OutcomeScore, RoutingHints, SchedulingHints } from "../types/optimization";
import type { OperationalMetrics, PipelineDashboardResponse } from "../types/operations";
import type {
  IntakeBootstrapResponse,
  IntakeDiscoverRequest,
  IntakeDiscoverResponse,
  IntakeReadyCheckRequest,
  IntakeReadyCheckResponse,
  IntakeRunCompareResponse,
  IntakeRunDetailResponse,
  IntakeRunListResponse,
  IntakeRunSummaryResponse,
  IntakeSavedPresetCreateRequest,
  IntakeSavedPresetListResponse,
  IntakeSavedPresetResponse,
  IntakeSavedPresetUpdateRequest
} from "../types/intake";
import type {
  DouyinAccount,
  DouyinAccountChallengeActionResponse,
  DouyinAccountCreateRequest,
  DouyinAccountDeleteResponse,
  DouyinAccountListResponse,
  DouyinBrowserConnectActiveSessionResponse,
  DouyinAccountRevalidateJobResponse,
  DouyinAccountRevalidateRequest,
  DouyinAccountUpdateRequest,
  DouyinAccountValidationResponse,
  DouyinBrowserConnectResetResponse,
  DouyinBrowserConnectSession,
  DouyinBrowserConnectStartRequest,
  DouyinCurrentPageCaptureRequest,
  DouyinCurrentPageCaptureResponse,
  DouyinCurrentPageDetectionResponse
} from "../types/douyin-accounts";
import type { DouyinExtensionStatusResponse } from "../types/douyin-extension-setup";
import type {
  DouyinExtensionCaptureRequest,
  DouyinExtensionCaptureResponse,
  DouyinExtensionDetectPageRequest,
  DouyinExtensionDetectPageResponse,
  DouyinExtensionManagerHistoryResponse
} from "../types/douyin-extension-manager";
import type {
  CaptureInboxActionRequest,
  CaptureInboxActionResponse,
  CaptureInboxItemQueryRequest,
  CaptureInboxProfileSummaryResponse,
  CaptureInboxProfileItemsResponse,
  CapturedItem,
  CapturedItemListResponse,
  CaptureSessionDetail,
  CaptureSessionItemsBySessionResponse,
  CaptureSessionListResponse,
  CaptureSessionStatus,
  CapturedItemStatus,
  StudioItemStatusFilter
} from "../types/capture-inbox";
import type {
  ReupQueueActionRequest,
  ReupQueueActionResponse,
  ReupQueueEnqueueRequest,
  ReupQueueEnqueueResponse,
  ReupQueueItem,
  ReupQueueListResponse,
  ReupQueueStatus
} from "../types/reup-queue";
import type {
  BatchOperationResponse,
  ExportPackage,
  ExportPackageCreateRequest,
  ExportPackageListResponse,
  PublishHandoff,
  PublishHandoffCreateRequest,
  PublishHandoffListResponse,
  ReupQueueBatchActionRequest
} from "../types/export-handoff";

import { SESSION_PRESENCE_COOKIE } from "./authPaths";
import {
  type AuthSurface,
  loginPathForSurface,
  SESSION_SURFACE_COOKIE,
  SESSION_SURFACE_STORAGE_KEY,
  surfaceForPath
} from "./authSurface";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const API_AUTH_TOKEN_STORAGE_KEY = "reup_douyin_api_auth_token";
const API_REFRESH_TOKEN_STORAGE_KEY = "reup_douyin_api_refresh_token";
const EXTENSION_AUTH_TOKEN_BRIDGE_EVENT = "REUP_DOUYIN_API_AUTH_TOKEN_SYNC";

export { SESSION_PRESENCE_COOKIE };
export type { AuthSurface };

let refreshInFlight: Promise<boolean> | null = null;

function syncApiAuthTokenToExtension(token: string | null): void {
  if (typeof window === "undefined") return;
  window.postMessage(
    {
      type: EXTENSION_AUTH_TOKEN_BRIDGE_EVENT,
      storageKey: API_AUTH_TOKEN_STORAGE_KEY,
      token: token && token.trim() ? token.trim() : null,
      syncedAt: new Date().toISOString()
    },
    window.location.origin
  );
}

function setSessionPresenceCookie(present: boolean): void {
  if (typeof document === "undefined") return;
  if (present) {
    document.cookie = `${SESSION_PRESENCE_COOKIE}=1; Path=/; SameSite=Lax`;
  } else {
    document.cookie = `${SESSION_PRESENCE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
  }
}

function setSessionSurfaceCookie(surface: AuthSurface | null): void {
  if (typeof document === "undefined") return;
  if (surface) {
    document.cookie = `${SESSION_SURFACE_COOKIE}=${surface}; Path=/; SameSite=Lax`;
    window.localStorage.setItem(SESSION_SURFACE_STORAGE_KEY, surface);
  } else {
    document.cookie = `${SESSION_SURFACE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
    window.localStorage.removeItem(SESSION_SURFACE_STORAGE_KEY);
  }
}

export function getAuthSurface(): AuthSurface | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_SURFACE_STORAGE_KEY);
  if (raw === "ops" || raw === "operator") return raw;
  return null;
}

export function setApiRefreshToken(token: string | null): void {
  if (typeof window === "undefined") return;
  const normalizedToken = token && token.trim() ? token.trim() : null;
  if (normalizedToken) {
    window.localStorage.setItem(API_REFRESH_TOKEN_STORAGE_KEY, normalizedToken);
  } else {
    window.localStorage.removeItem(API_REFRESH_TOKEN_STORAGE_KEY);
  }
}

export function getApiRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(API_REFRESH_TOKEN_STORAGE_KEY);
}

export function setApiAuthToken(token: string | null): void {
  if (typeof window === "undefined") return;
  const normalizedToken = token && token.trim() ? token.trim() : null;
  if (normalizedToken) {
    window.localStorage.setItem(API_AUTH_TOKEN_STORAGE_KEY, normalizedToken);
    setSessionPresenceCookie(true);
  } else {
    window.localStorage.removeItem(API_AUTH_TOKEN_STORAGE_KEY);
    setApiRefreshToken(null);
    setSessionPresenceCookie(false);
    setSessionSurfaceCookie(null);
  }
  syncApiAuthTokenToExtension(normalizedToken);
}

export function persistAuthSession(
  accessToken: string,
  refreshToken: string | null | undefined,
  surface: AuthSurface = "operator"
): void {
  setApiAuthToken(accessToken);
  if (refreshToken) setApiRefreshToken(refreshToken);
  setSessionSurfaceCookie(surface);
}

export function getApiAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(API_AUTH_TOKEN_STORAGE_KEY);
}

function withAuthHeaders(init: RequestInit = {}): RequestInit {
  const token = getApiAuthToken();
  if (!token) return init;
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const path = window.location.pathname || "/";
  if (path.startsWith("/auth")) return;
  const surface = getAuthSurface() ?? surfaceForPath(path);
  setApiAuthToken(null);
  const next = encodeURIComponent(path + (window.location.search || ""));
  window.location.replace(`${loginPathForSurface(surface)}?next=${next}`);
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = getApiRefreshToken();
  if (!refreshToken) return false;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken })
        });
        if (!response.ok) return false;
        const payload = (await response.json()) as AuthTokenApiResponse;
        const surface = payload.client === "ops" ? "ops" : "operator";
        persistAuthSession(payload.access_token, payload.refresh_token, surface);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

async function apiFetch(input: string, init: RequestInit = {}, allowRefresh = true): Promise<Response> {
  const response = await fetch(input, withAuthHeaders(init));
  if (response.status !== 401 || typeof window === "undefined") {
    return response;
  }
  if (allowRefresh && (await refreshAccessToken())) {
    return apiFetch(input, init, false);
  }
  redirectToLogin();
  return response;
}

export type AuthMembership = {
  workspaceId: string;
  workspaceSlug: string;
  role: string;
  isActive: boolean;
};

export type AuthTokenResponse = {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  expiresAt: number;
  refreshExpiresAt: number;
  workspaceId: string;
  subject: string;
  roles: string[];
  operatorId?: string | null;
  displayName?: string | null;
  client: AuthSurface | "api-ui" | string;
  audience?: string | null;
  scopes: string[];
};

export type AuthMeResponse = {
  subject: string;
  email: string;
  workspaceId: string;
  workspaceSlug: string;
  roles: string[];
  operatorId: string;
  displayName: string | null;
  memberships: AuthMembership[];
  client?: string | null;
  audience?: string | null;
  scopes?: string[];
};

export type AuthLoginRequest = {
  email: string;
  password: string;
  workspaceSlug: string;
  client?: "operator" | "ops";
};

export type AuthRegisterRequest = AuthLoginRequest & {
  displayName?: string;
};

type AuthTokenApiResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_at: number;
  refresh_expires_at: number;
  workspace_id: string;
  subject: string;
  roles: string[];
  operator_id?: string | null;
  display_name?: string | null;
  client?: string;
  audience?: string | null;
  scopes?: string[];
};

type AuthMeApiResponse = {
  subject: string;
  email: string;
  workspace_id: string;
  workspace_slug: string;
  roles: string[];
  operator_id: string;
  display_name: string | null;
  memberships?: Array<{
    workspace_id: string;
    workspace_slug: string;
    role: string;
    is_active: boolean;
  }>;
};

function mapAuthTokenResponse(payload: AuthTokenApiResponse): AuthTokenResponse {
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    tokenType: payload.token_type,
    expiresAt: payload.expires_at,
    refreshExpiresAt: payload.refresh_expires_at,
    workspaceId: payload.workspace_id,
    subject: payload.subject,
    roles: payload.roles,
    operatorId: payload.operator_id ?? null,
    displayName: payload.display_name ?? null,
    client: payload.client ?? "operator",
    audience: payload.audience ?? null,
    scopes: payload.scopes ?? []
  };
}

function surfaceFromClient(client: string | undefined): AuthSurface {
  return client === "ops" ? "ops" : "operator";
}

export async function loginWithPassword(payload: AuthLoginRequest): Promise<AuthTokenResponse> {
  const client = payload.client ?? "operator";
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: payload.email,
      password: payload.password,
      workspace_slug: payload.workspaceSlug,
      client
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Login failed"));
  }
  const mapped = mapAuthTokenResponse((await response.json()) as AuthTokenApiResponse);
  persistAuthSession(mapped.accessToken, mapped.refreshToken, surfaceFromClient(mapped.client));
  return mapped;
}

export async function registerWithPassword(payload: AuthRegisterRequest): Promise<AuthTokenResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      display_name: payload.displayName,
      email: payload.email,
      password: payload.password,
      workspace_slug: payload.workspaceSlug,
      client: "operator"
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Registration failed"));
  }
  const mapped = mapAuthTokenResponse((await response.json()) as AuthTokenApiResponse);
  persistAuthSession(mapped.accessToken, mapped.refreshToken, "operator");
  return mapped;
}

export async function logoutSession(): Promise<void> {
  const refreshToken = getApiRefreshToken();
  try {
    if (refreshToken) {
      await fetch(`${API_BASE_URL}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken })
      });
    }
  } catch {
    // Best-effort revoke; clear local session regardless.
  } finally {
    setApiAuthToken(null);
  }
}

export async function acceptInvite(payload: {
  inviteToken: string;
  password: string;
  displayName?: string;
}): Promise<AuthTokenResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/invites/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      invite_token: payload.inviteToken,
      password: payload.password,
      display_name: payload.displayName
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Invite accept failed"));
  }
  const mapped = mapAuthTokenResponse((await response.json()) as AuthTokenApiResponse);
  persistAuthSession(mapped.accessToken, mapped.refreshToken, "operator");
  return mapped;
}

export async function fetchAuthMe(): Promise<AuthMeResponse> {
  const response = await apiFetch(`${API_BASE_URL}/auth/me`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load auth profile"));
  }
  const payload = (await response.json()) as AuthMeApiResponse;
  return {
    subject: payload.subject,
    email: payload.email,
    workspaceId: payload.workspace_id,
    workspaceSlug: payload.workspace_slug,
    roles: payload.roles,
    operatorId: payload.operator_id,
    displayName: payload.display_name,
    memberships: (payload.memberships ?? []).map((m) => ({
      workspaceId: m.workspace_id,
      workspaceSlug: m.workspace_slug,
      role: m.role,
      isActive: m.is_active
    }))
  };
}

export type WorkspaceMember = {
  operatorId: string;
  email: string;
  displayName: string | null;
  role: string;
  isActive: boolean;
  createdAt: string | null;
  phone: string | null;
  address: string | null;
  notes: string | null;
  lastSeenAt: string | null;
};

export type WorkspaceInvite = {
  inviteId: string;
  email: string;
  role: string;
  status: string;
  expiresAt: string;
  createdAt: string | null;
  note: string | null;
};

type WorkspaceMemberApi = {
  operator_id: string;
  email: string;
  display_name?: string | null;
  role: string;
  is_active: boolean;
  created_at?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
  last_seen_at?: string | null;
};

type WorkspaceInviteApi = {
  invite_id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  created_at?: string | null;
  note?: string | null;
};

function mapWorkspaceMember(row: WorkspaceMemberApi): WorkspaceMember {
  return {
    operatorId: row.operator_id,
    email: row.email,
    displayName: row.display_name ?? null,
    role: row.role,
    isActive: row.is_active,
    createdAt: row.created_at ?? null,
    phone: row.phone ?? null,
    address: row.address ?? null,
    notes: row.notes ?? null,
    lastSeenAt: row.last_seen_at ?? null
  };
}

function mapWorkspaceInvite(row: WorkspaceInviteApi): WorkspaceInvite {
  return {
    inviteId: row.invite_id,
    email: row.email,
    role: row.role,
    status: row.status,
    expiresAt: row.expires_at,
    createdAt: row.created_at ?? null,
    note: row.note ?? null
  };
}

export async function fetchWorkspaceMembers(): Promise<WorkspaceMember[]> {
  const response = await apiFetch(`${API_BASE_URL}/auth/workspace/members`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load workspace members"));
  }
  const payload = (await response.json()) as { members?: WorkspaceMemberApi[] };
  return (payload.members ?? []).map(mapWorkspaceMember);
}

export async function fetchWorkspaceInvites(): Promise<WorkspaceInvite[]> {
  const response = await apiFetch(`${API_BASE_URL}/auth/workspace/invites`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load workspace invites"));
  }
  const payload = (await response.json()) as { invites?: WorkspaceInviteApi[] };
  return (payload.invites ?? []).map(mapWorkspaceInvite);
}

export async function createWorkspaceInvite(payload: {
  email: string;
  role: string;
  note?: string;
}): Promise<{ inviteId: string; email: string; role: string; expiresAt: string; inviteToken: string }> {
  const response = await apiFetch(`${API_BASE_URL}/auth/invites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: payload.email,
      role: payload.role,
      note: payload.note
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create invite"));
  }
  const body = (await response.json()) as {
    invite_id: string;
    email: string;
    role: string;
    expires_at: string;
    invite_token: string;
  };
  return {
    inviteId: body.invite_id,
    email: body.email,
    role: body.role,
    expiresAt: body.expires_at,
    inviteToken: body.invite_token
  };
}

export async function revokeWorkspaceInvite(inviteId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/auth/workspace/invites/${encodeURIComponent(inviteId)}/revoke`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to revoke invite"));
  }
}

export async function updateWorkspaceMember(
  operatorId: string,
  patch: {
    role?: string;
    isActive?: boolean;
    displayName?: string | null;
    phone?: string | null;
    address?: string | null;
    notes?: string | null;
  }
): Promise<WorkspaceMember> {
  const body: Record<string, unknown> = {};
  if (patch.role !== undefined) body.role = patch.role;
  if (patch.isActive !== undefined) body.is_active = patch.isActive;
  if (patch.displayName !== undefined) body.display_name = patch.displayName;
  if (patch.phone !== undefined) body.phone = patch.phone;
  if (patch.address !== undefined) body.address = patch.address;
  if (patch.notes !== undefined) body.notes = patch.notes;
  const response = await apiFetch(`${API_BASE_URL}/auth/workspace/members/${encodeURIComponent(operatorId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to update member"));
  }
  return mapWorkspaceMember((await response.json()) as WorkspaceMemberApi);
}

export async function resetWorkspaceMemberPassword(
  operatorId: string
): Promise<{ operatorId: string; email: string; temporaryPassword: string }> {
  const response = await apiFetch(
    `${API_BASE_URL}/auth/workspace/members/${encodeURIComponent(operatorId)}/reset-password`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to reset member password"));
  }
  const body = (await response.json()) as {
    operator_id: string;
    email: string;
    temporary_password: string;
  };
  return {
    operatorId: body.operator_id,
    email: body.email,
    temporaryPassword: body.temporary_password
  };
}

export async function rotateWorkspaceInvite(
  inviteId: string
): Promise<{ inviteId: string; email: string; role: string; expiresAt: string; inviteToken: string }> {
  const response = await apiFetch(
    `${API_BASE_URL}/auth/workspace/invites/${encodeURIComponent(inviteId)}/rotate`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to rotate invite link"));
  }
  const body = (await response.json()) as {
    invite_id: string;
    email: string;
    role: string;
    expires_at: string;
    invite_token: string;
  };
  return {
    inviteId: body.invite_id,
    email: body.email,
    role: body.role,
    expiresAt: body.expires_at,
    inviteToken: body.invite_token
  };
}

export type CandidateListResult = {
  candidates: Candidate[];
  statusCounts: CandidateListResponse["status_counts"];
  totalCount: number;
  view: "summary" | "detail";
};

function summaryToCandidate(summary: CandidateSummary): Candidate {
  return {
    id: summary.id,
    source_video_id: summary.source_video_id,
    status: summary.status,
    score: summary.score,
    score_version: null,
    score_label: summary.score_label,
    score_breakdown_json: null,
    score_reason: null,
    preset_name: summary.preset_name,
    filter_config_json: null,
    inclusion_reasons_json: null,
    exclusion_reasons_json: null,
    warnings_json: null,
    evaluated_at: summary.evaluated_at ?? null,
    priority: summary.priority,
    metadata_json: null,
    created_at: summary.updated_at,
    updated_at: summary.updated_at,
    source_video: summary.source_video,
    reup_score: summary.reup_score ?? null,
    caption: summary.caption ?? summary.source_video?.caption ?? null,
    thumbnail_url: summary.thumbnail_url ?? null,
    posted_display: summary.posted_display ?? null,
    duration_text: summary.duration_text ?? null,
    estimated_views_display: summary.estimated_views_display ?? null,
    estimated_views_min: summary.estimated_views_min ?? null,
    estimated_views_max: summary.estimated_views_max ?? null,
    estimated_views_mid: summary.estimated_views_mid ?? null,
    like_count: summary.like_count ?? null,
    comment_count: summary.comment_count ?? null,
    share_count: summary.share_count ?? null,
    engagement_rate: summary.engagement_rate ?? null,
    duration_seconds: summary.duration_seconds ?? null,
    aweme_id: summary.aweme_id ?? summary.source_video_external_id ?? null,
    source_video_external_id: summary.source_video_external_id ?? summary.source_video?.source_video_external_id ?? null,
    source_url: summary.source_url ?? summary.source_video?.source_url ?? null,
    review_status: summary.review_status ?? null,
    decision_status: summary.decision_status ?? null,
    in_reup_queue: summary.in_reup_queue ?? false,
    reup_queue_item_id: summary.reup_queue_item_id ?? null,
    reup_queue_status: summary.reup_queue_status ?? null
  };
}

export async function fetchCandidates(
  filters: CandidateFilters,
  options?: { limit?: number; offset?: number }
): Promise<CandidateListResult> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.minScore) params.set("min_score", filters.minScore);
  if (filters.maxScore) params.set("max_score", filters.maxScore);
  if (filters.sourceProfileId) params.set("source_profile_id", filters.sourceProfileId);
  const search = filters.search.trim();
  if (search) params.set("search", search);
  params.set("view", "summary");
  params.set("hydrate", "false");
  params.set("limit", String(options?.limit ?? 200));
  if (options?.offset) params.set("offset", String(options.offset));

  const response = await apiFetch(`${API_BASE_URL}/candidates?${params.toString()}`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`Failed to load candidates: ${response.status}`);
  }
  const payload = (await response.json()) as CandidateListResponse;
  const summaries = payload.candidates as CandidateSummary[];
  return {
    candidates: summaries.map(summaryToCandidate),
    statusCounts: payload.status_counts ?? {},
    totalCount: payload.total_count,
    view: payload.view
  };
}

export async function fetchCandidateDetail(candidateId: string): Promise<Candidate> {
  const response = await apiFetch(`${API_BASE_URL}/candidates/${candidateId}`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`Failed to load candidate detail: ${response.status}`);
  }
  return (await response.json()) as Candidate;
}

export async function deleteCandidate(candidateId: string): Promise<CandidateDeleteResponse> {
  const response = await apiFetch(`${API_BASE_URL}/candidates/${candidateId}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to remove candidate from Review Board"));
  }
  return (await response.json()) as CandidateDeleteResponse;
}

export async function fetchFilterPresets() {
  const response = await apiFetch(`${API_BASE_URL}/filter-presets`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load filter presets: ${response.status}`);
  }
  const payload = (await response.json()) as FilterPresetListResponse;
  return payload.presets;
}

export async function discoverIntakeCandidates(payload: IntakeDiscoverRequest): Promise<IntakeDiscoverResponse> {
  const response = await apiFetch(`${API_BASE_URL}/intake/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to discover intake candidates"));
  }
  return (await response.json()) as IntakeDiscoverResponse;
}

export async function runIntakeReadyCheck(payload: IntakeReadyCheckRequest): Promise<IntakeReadyCheckResponse> {
  const response = await apiFetch(`${API_BASE_URL}/intake/ready-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to run intake ready check"));
  }
  return (await response.json()) as IntakeReadyCheckResponse;
}

export async function fetchIntakeBootstrap(workspaceId?: string): Promise<IntakeBootstrapResponse> {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE_URL}/intake/bootstrap${query ? `?${query}` : ""}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load intake bootstrap"));
  }
  return (await response.json()) as IntakeBootstrapResponse;
}

export async function fetchIntakeSavedPresets(workspaceId?: string): Promise<IntakeSavedPresetResponse[]> {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  const query = params.toString();
  const response = await apiFetch(`${API_BASE_URL}/intake/saved-presets${query ? `?${query}` : ""}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load intake saved presets"));
  }
  const payload = (await response.json()) as IntakeSavedPresetListResponse;
  return payload.presets;
}

export async function createIntakeSavedPreset(payload: IntakeSavedPresetCreateRequest): Promise<IntakeSavedPresetResponse> {
  const response = await apiFetch(`${API_BASE_URL}/intake/saved-presets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create intake saved preset"));
  }
  return (await response.json()) as IntakeSavedPresetResponse;
}

export async function updateIntakeSavedPreset(
  presetId: string,
  payload: IntakeSavedPresetUpdateRequest
): Promise<IntakeSavedPresetResponse> {
  const response = await apiFetch(`${API_BASE_URL}/intake/saved-presets/${presetId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to update intake saved preset"));
  }
  return (await response.json()) as IntakeSavedPresetResponse;
}

export async function deleteIntakeSavedPreset(presetId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/intake/saved-presets/${presetId}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete intake saved preset"));
  }
}

export async function fetchIntakeRuns(limit = 12, workspaceId?: string): Promise<IntakeRunSummaryResponse[]> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (workspaceId) params.set("workspace_id", workspaceId);
  const response = await apiFetch(`${API_BASE_URL}/intake/runs?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load intake runs"));
  }
  const payload = (await response.json()) as IntakeRunListResponse;
  return payload.runs;
}

export async function fetchIntakeRun(crawlSessionId: string): Promise<IntakeRunDetailResponse> {
  const response = await apiFetch(`${API_BASE_URL}/intake/runs/${crawlSessionId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load intake run detail"));
  }
  return (await response.json()) as IntakeRunDetailResponse;
}

export async function compareIntakeRuns(leftRunId: string, rightRunId: string): Promise<IntakeRunCompareResponse> {
  const params = new URLSearchParams({ left_run_id: leftRunId, right_run_id: rightRunId });
  const response = await apiFetch(`${API_BASE_URL}/intake/runs/compare?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to compare intake runs"));
  }
  return (await response.json()) as IntakeRunCompareResponse;
}

export function getDouyinExtensionDownloadUrl(): string {
  return `${API_BASE_URL}/douyin-extension/download`;
}

export async function fetchDouyinExtensionStatus(): Promise<DouyinExtensionStatusResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-extension/status`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Douyin extension status"));
  }
  return (await response.json()) as DouyinExtensionStatusResponse;
}

export async function checkDouyinExtensionStatus(): Promise<DouyinExtensionStatusResponse> {
  return fetchDouyinExtensionStatus();
}

export async function fetchDouyinExtensionHistory(limit = 10): Promise<DouyinExtensionManagerHistoryResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await apiFetch(`${API_BASE_URL}/douyin-extension/history?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Douyin extension history"));
  }
  return (await response.json()) as DouyinExtensionManagerHistoryResponse;
}

export async function detectDouyinExtensionPage(payload: DouyinExtensionDetectPageRequest): Promise<DouyinExtensionDetectPageResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-extension/detect-page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to detect Douyin extension current page"));
  }
  return (await response.json()) as DouyinExtensionDetectPageResponse;
}

export async function captureDouyinExtensionPage(payload: DouyinExtensionCaptureRequest): Promise<DouyinExtensionCaptureResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-extension/capture-current-page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to capture Douyin extension current page"));
  }
  return (await response.json()) as DouyinExtensionCaptureResponse;
}

export async function fetchCaptureInboxSessions(filters: { status?: CaptureSessionStatus; limit?: number; offset?: number } = {}): Promise<CaptureSessionListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(filters.limit ?? 20));
  params.set("offset", String(filters.offset ?? 0));
  const response = await apiFetch(`${API_BASE_URL}/capture-inbox/sessions?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load capture inbox sessions"));
  }
  return (await response.json()) as CaptureSessionListResponse;
}

export async function fetchCaptureInboxSession(captureSessionId: string): Promise<CaptureSessionDetail> {
  const response = await apiFetch(`${API_BASE_URL}/capture-inbox/sessions/${encodeURIComponent(captureSessionId)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load capture inbox session"));
  }
  return (await response.json()) as CaptureSessionDetail;
}

export async function fetchCaptureInboxProfileSummary(profileUrl: string): Promise<CaptureInboxProfileSummaryResponse> {
  const params = new URLSearchParams({ profile_url: profileUrl });
  const response = await apiFetch(
    `${API_BASE_URL}/douyin-extension/capture-inbox/profile-summary?${params.toString()}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load capture inbox profile summary"));
  }
  return (await response.json()) as CaptureInboxProfileSummaryResponse;
}

export async function fetchCaptureInboxProfileItems(filters: {
  profileUrl: string;
  limit?: number;
  offset?: number;
}): Promise<CaptureInboxProfileItemsResponse> {
  const params = new URLSearchParams({ profile_url: filters.profileUrl });
  params.set("limit", String(filters.limit ?? 100));
  params.set("offset", String(filters.offset ?? 0));
  const response = await apiFetch(
    `${API_BASE_URL}/douyin-extension/capture-inbox/profile-items?${params.toString()}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load capture inbox profile items"));
  }
  return (await response.json()) as CaptureInboxProfileItemsResponse;
}

export async function fetchCaptureInboxItem(itemId: string): Promise<CapturedItem> {
  const response = await apiFetch(`${API_BASE_URL}/capture-inbox/items/${encodeURIComponent(itemId)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load capture inbox item details"));
  }
  return (await response.json()) as CapturedItem;
}

export async function fetchCaptureSessionItemsBySession(captureSessionId: string): Promise<CaptureSessionItemsBySessionResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-extension/capture-sessions/${encodeURIComponent(captureSessionId)}/items`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load capture-session items"));
  }
  return (await response.json()) as CaptureSessionItemsBySessionResponse;
}

export async function deleteCaptureInboxSession(captureSessionId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/capture-inbox/sessions/${encodeURIComponent(captureSessionId)}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete capture inbox session"));
  }
}

export async function fetchCaptureInboxItems(filters: {
  captureSessionId?: string;
  profileUrl?: string;
  status?: CapturedItemStatus;
  studioStatus?: StudioItemStatusFilter;
  limit?: number;
  offset?: number;
} = {}): Promise<CapturedItemListResponse> {
  const params = new URLSearchParams();
  if (filters.captureSessionId) params.set("capture_session_id", filters.captureSessionId);
  if (filters.profileUrl) params.set("profile_url", filters.profileUrl);
  if (filters.status) params.set("status", filters.status);
  if (filters.studioStatus) params.set("studio_status", filters.studioStatus);
  params.set("limit", String(filters.limit ?? 100));
  params.set("offset", String(filters.offset ?? 0));
  const response = await apiFetch(`${API_BASE_URL}/capture-inbox/items?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load capture inbox items"));
  }
  return (await response.json()) as CapturedItemListResponse;
}

export async function queryCaptureInboxItems(payload: CaptureInboxItemQueryRequest): Promise<CapturedItemListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/capture-inbox/items/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to query capture inbox items"));
  }
  return (await response.json()) as CapturedItemListResponse;
}

export async function runCaptureInboxAction(captureSessionId: string, payload: CaptureInboxActionRequest): Promise<CaptureInboxActionResponse> {
  const response = await apiFetch(`${API_BASE_URL}/capture-inbox/sessions/${encodeURIComponent(captureSessionId)}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to run capture inbox action"));
  }
  return (await response.json()) as CaptureInboxActionResponse;
}

export async function fetchReupQueueItems(filters: {
  status?: ReupQueueStatus;
  statuses?: ReupQueueStatus[];
  sort?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<ReupQueueListResponse> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.statuses?.length) {
    for (const status of filters.statuses) params.append("statuses", status);
  }
  if (filters.sort) params.set("sort", filters.sort);
  params.set("limit", String(filters.limit ?? 100));
  params.set("offset", String(filters.offset ?? 0));
  const response = await apiFetch(`${API_BASE_URL}/reup-queue/items?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Reup Queue"));
  }
  const payload = (await response.json()) as ReupQueueListResponse;
  return {
    ...payload,
    items: payload.items ?? [],
    total_count: Number(payload.total_count ?? 0),
    limit: Number(payload.limit ?? filters.limit ?? 100),
    offset: Number(payload.offset ?? filters.offset ?? 0),
    status_counts: payload.status_counts ?? {}
  };
}

export async function fetchReupQueueItem(itemId: string): Promise<ReupQueueItem> {
  const response = await apiFetch(`${API_BASE_URL}/reup-queue/items/${encodeURIComponent(itemId)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Reup Queue item"));
  }
  return (await response.json()) as ReupQueueItem;
}

export async function runReupQueueAction(itemId: string, payload: ReupQueueActionRequest): Promise<ReupQueueActionResponse> {
  const response = await apiFetch(`${API_BASE_URL}/reup-queue/items/${encodeURIComponent(itemId)}/actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to run Reup Queue action"));
  }
  return (await response.json()) as ReupQueueActionResponse;
}

export async function runReupQueueBatchAction(payload: ReupQueueBatchActionRequest): Promise<BatchOperationResponse> {
  const response = await apiFetch(`${API_BASE_URL}/reup-queue/batch-actions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to run Reup Queue batch action"));
  }
  return (await response.json()) as BatchOperationResponse;
}

export type ReupQueuePurgeResponse = {
  requested_count: number;
  purged_count: number;
  skipped_count: number;
  skipped_item_ids: string[];
};

export async function purgeClearableReupQueueItems(payload: { item_ids?: string[] | null; scope?: "clearable" | "selected" } = {}): Promise<ReupQueuePurgeResponse> {
  const response = await apiFetch(`${API_BASE_URL}/reup-queue/purge-clearable`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      item_ids: payload.item_ids ?? null,
      scope: payload.scope ?? (payload.item_ids?.length ? "selected" : "clearable")
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to purge Reup Queue items"));
  }
  return (await response.json()) as ReupQueuePurgeResponse;
}

export async function createExportPackage(payload: ExportPackageCreateRequest): Promise<ExportPackage> {
  const response = await apiFetch(`${API_BASE_URL}/export-packages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create Export Package"));
  }
  return (await response.json()) as ExportPackage;
}

export async function fetchExportPackages(limit = 100): Promise<ExportPackageListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/export-packages?limit=${encodeURIComponent(String(limit))}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Export Packages"));
  }
  return (await response.json()) as ExportPackageListResponse;
}

export async function fetchExportPackage(packageId: string): Promise<ExportPackage> {
  const response = await apiFetch(`${API_BASE_URL}/export-packages/${encodeURIComponent(packageId)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Export Package"));
  }
  return (await response.json()) as ExportPackage;
}

export async function createPublishHandoff(payload: PublishHandoffCreateRequest): Promise<PublishHandoff> {
  const response = await apiFetch(`${API_BASE_URL}/publish-handoffs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create Publish Handoff"));
  }
  return (await response.json()) as PublishHandoff;
}

export async function fetchPublishHandoffs(limit = 100): Promise<PublishHandoffListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/publish-handoffs?limit=${encodeURIComponent(String(limit))}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Publish Handoffs"));
  }
  return (await response.json()) as PublishHandoffListResponse;
}

export async function fetchPublishHandoff(handoffId: string): Promise<PublishHandoff> {
  const response = await apiFetch(`${API_BASE_URL}/publish-handoffs/${encodeURIComponent(handoffId)}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Publish Handoff"));
  }
  return (await response.json()) as PublishHandoff;
}

export async function enqueueReupCandidates(payload: ReupQueueEnqueueRequest): Promise<ReupQueueEnqueueResponse> {
  const response = await apiFetch(`${API_BASE_URL}/reup-queue/enqueue-candidates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to send approved candidates to Reup Queue"));
  }
  return (await response.json()) as ReupQueueEnqueueResponse;
}

export async function fetchDouyinAccounts(): Promise<DouyinAccount[]> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load Douyin accounts: ${response.status}`);
  }
  const payload = (await response.json()) as DouyinAccountListResponse;
  return payload.accounts;
}

export async function createDouyinAccount(payload: DouyinAccountCreateRequest): Promise<DouyinAccount> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save Douyin account"));
  }
  return (await response.json()) as DouyinAccount;
}

export async function updateDouyinAccount(accountId: string, payload: DouyinAccountUpdateRequest): Promise<DouyinAccount> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to update Douyin account"));
  }
  return (await response.json()) as DouyinAccount;
}

export async function validateDouyinAccount(accountId: string): Promise<DouyinAccountValidationResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to validate Douyin account"));
  }
  return (await response.json()) as DouyinAccountValidationResponse;
}

export async function detectDouyinCurrentPage(accountId: string): Promise<DouyinCurrentPageDetectionResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}/current-page`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to detect Douyin current page"));
  }
  return (await response.json()) as DouyinCurrentPageDetectionResponse;
}

export async function captureDouyinCurrentPage(
  accountId: string,
  payload: DouyinCurrentPageCaptureRequest = {}
): Promise<DouyinCurrentPageCaptureResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}/current-page/capture`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persist: payload.persist ?? true, max_videos: payload.max_videos ?? 50, ...payload })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to capture Douyin current page"));
  }
  return (await response.json()) as DouyinCurrentPageCaptureResponse;
}

export async function markDouyinAccountChallengeSolved(accountId: string): Promise<DouyinAccountChallengeActionResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}/challenge-solved`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to mark Douyin challenge solved"));
  }
  return (await response.json()) as DouyinAccountChallengeActionResponse;
}

export async function recheckDouyinAccountChallenge(accountId: string): Promise<DouyinAccountChallengeActionResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}/challenge-recheck`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to recheck Douyin challenge"));
  }
  return (await response.json()) as DouyinAccountChallengeActionResponse;
}

export async function revalidateDueDouyinAccounts(payload: DouyinAccountRevalidateRequest = {}): Promise<DouyinAccount[]> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/revalidate-due`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ due_only: payload.due_only ?? true, workspace_id: payload.workspace_id ?? null })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to revalidate Douyin accounts"));
  }
  const result = (await response.json()) as { accounts: DouyinAccount[] };
  return result.accounts;
}

export async function enqueueDouyinAccountRevalidateJob(accountId: string): Promise<DouyinAccountRevalidateJobResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}/revalidate-job`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to queue Douyin account revalidate job"));
  }
  return (await response.json()) as DouyinAccountRevalidateJobResponse;
}

export async function enqueueDouyinAccountsRevalidateDueJob(payload: DouyinAccountRevalidateRequest = {}): Promise<DouyinAccountRevalidateJobResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/revalidate-due/job`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ due_only: payload.due_only ?? true, workspace_id: payload.workspace_id ?? null })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to queue Douyin account health sweep"));
  }
  return (await response.json()) as DouyinAccountRevalidateJobResponse;
}

export async function disableDouyinAccount(accountId: string): Promise<DouyinAccount> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}/disable`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to disable Douyin account"));
  }
  return (await response.json()) as DouyinAccount;
}

export async function deleteDouyinAccount(accountId: string): Promise<DouyinAccountDeleteResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/${accountId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete Douyin account"));
  }
  return (await response.json()) as DouyinAccountDeleteResponse;
}

export async function startDouyinBrowserConnect(payload: DouyinBrowserConnectStartRequest): Promise<DouyinBrowserConnectSession> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/browser-connect/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to start Douyin browser connect"));
  }
  return (await response.json()) as DouyinBrowserConnectSession;
}

export async function fetchActiveDouyinBrowserConnect(): Promise<DouyinBrowserConnectActiveSessionResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/browser-connect/active`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load active Douyin browser connect"));
  }
  return (await response.json()) as DouyinBrowserConnectActiveSessionResponse;
}

export async function fetchDouyinBrowserConnect(connectSessionId: string): Promise<DouyinBrowserConnectSession> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/browser-connect/${connectSessionId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Douyin browser connect"));
  }
  return (await response.json()) as DouyinBrowserConnectSession;
}

export async function restartDouyinBrowserConnect(connectSessionId: string, payload: DouyinBrowserConnectStartRequest): Promise<DouyinBrowserConnectSession> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/browser-connect/${connectSessionId}/restart`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to restart Douyin browser connect"));
  }
  return (await response.json()) as DouyinBrowserConnectSession;
}

export async function resetDouyinBrowserConnectState(): Promise<DouyinBrowserConnectResetResponse> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/browser-connect/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to reset Douyin browser connect state"));
  }
  return (await response.json()) as DouyinBrowserConnectResetResponse;
}

export async function retryDouyinBrowserConnectValidation(connectSessionId: string): Promise<DouyinBrowserConnectSession> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/browser-connect/${connectSessionId}/retry-validation`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to retry Douyin browser connect validation"));
  }
  return (await response.json()) as DouyinBrowserConnectSession;
}

export async function cancelDouyinBrowserConnect(connectSessionId: string): Promise<DouyinBrowserConnectSession> {
  const response = await apiFetch(`${API_BASE_URL}/douyin-accounts/browser-connect/${connectSessionId}/cancel`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to cancel Douyin browser connect"));
  }
  return (await response.json()) as DouyinBrowserConnectSession;
}

export async function fetchJobs(
  status?: JobStatus,
  options:
    | number
    | {
        limit?: number;
        offset?: number;
        sourceVideoId?: string;
        jobType?: JobType;
      } = {}
): Promise<JobListResponse> {
  const normalized =
    typeof options === "number"
      ? { limit: options, offset: 0, sourceVideoId: undefined as string | undefined, jobType: undefined as JobType | undefined }
      : {
          limit: options.limit ?? 50,
          offset: options.offset ?? 0,
          sourceVideoId: options.sourceVideoId,
          jobType: options.jobType
        };
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (normalized.sourceVideoId) params.set("source_video_id", normalized.sourceVideoId);
  if (normalized.jobType) params.set("job_type", normalized.jobType);
  params.set("limit", String(normalized.limit));
  params.set("offset", String(normalized.offset));

  const response = await apiFetch(`${API_BASE_URL}/jobs?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load jobs: ${response.status}`);
  }
  const payload = (await response.json()) as JobListResponse;
  return {
    jobs: payload.jobs ?? [],
    total_count: Number(payload.total_count ?? payload.jobs?.length ?? 0),
    limit: Number(payload.limit ?? normalized.limit),
    offset: Number(payload.offset ?? normalized.offset),
  };
}

export async function fetchJob(jobId: string): Promise<Job> {
  const response = await apiFetch(`${API_BASE_URL}/jobs/${jobId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load job"));
  }
  return (await response.json()) as Job;
}

export async function cancelJob(jobId: string): Promise<Job> {
  const response = await apiFetch(`${API_BASE_URL}/jobs/${jobId}/cancel`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to cancel job"));
  }
  return (await response.json()) as Job;
}

export async function deleteJob(jobId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/jobs/${jobId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete job"));
  }
}

export async function retryJob(jobId: string): Promise<Job> {
  const response = await apiFetch(`${API_BASE_URL}/jobs/${jobId}/retry`, { method: "POST" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to retry job"));
  }
  return (await response.json()) as Job;
}

export async function fetchOperationalMetrics(): Promise<OperationalMetrics> {
  const response = await apiFetch(`${API_BASE_URL}/ops/metrics`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load operational metrics: ${response.status}`);
  }
  return (await response.json()) as OperationalMetrics;
}

export type PromptProfileSummary = {
  id: string;
  name: string;
  prompt: string;
  is_active: boolean;
};

export type TranslationPromptResponse = {
  prompt: string;
  source: string;
  updated?: boolean;
  active_profile_id?: string;
  active_profile_name?: string;
  profiles?: PromptProfileSummary[];
  focus_profile_id?: string | null;
};

export async function fetchTranslationPrompt(): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-prompt`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load translation prompt"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function saveTranslationPrompt(prompt: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-prompt`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save translation prompt"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function createTranslationPromptProfile(name: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-prompt/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create translation prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function fetchTranslationPromptProfile(profileId: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-prompt/profiles/${encodeURIComponent(profileId)}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load translation prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function saveTranslationPromptProfile(
  profileId: string,
  prompt: string
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-prompt/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt })
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save translation prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function renameTranslationPromptProfile(
  profileId: string,
  name: string
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-prompt/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to rename translation prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function activateTranslationPromptProfile(
  profileId: string
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-prompt/profiles/${encodeURIComponent(profileId)}/activate`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to switch translation prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function reorderTranslationPromptProfiles(
  profileIds: string[]
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-prompt/profiles/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_ids: profileIds })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to reorder translation prompt setups"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function deleteTranslationPromptProfile(
  profileId: string
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-prompt/profiles/${encodeURIComponent(profileId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete translation prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export type TranslationAiProfileSummary = {
  id: string;
  name: string;
  enabled: boolean;
  provider: string;
  model: string;
  api_key_set: boolean;
  api_key_masked: string;
  api_key?: string;
  base_url: string;
  timeout_seconds: number;
  fallback_provider: string;
  fallback_model: string;
  is_active: boolean;
};

export type TranslationAiResponse = {
  enabled: boolean;
  provider: string;
  model: string;
  api_key_set: boolean;
  api_key_masked: string;
  api_key?: string;
  base_url: string;
  timeout_seconds: number;
  fallback_provider: string;
  fallback_model: string;
  source: string;
  updated?: boolean;
  active_profile_id?: string | null;
  active_profile_name?: string | null;
  profiles?: TranslationAiProfileSummary[];
  focus_profile_id?: string | null;
};

export type TranslationAiPayload = {
  enabled: boolean;
  provider: string;
  model: string;
  api_key?: string | null;
  clear_api_key?: boolean;
  base_url: string;
  timeout_seconds: number;
  fallback_provider: string;
  fallback_model: string;
};

export type TranslationAiTestResponse = {
  ok: boolean;
  provider: string;
  detail: string;
};

export async function fetchTranslationAi(): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-ai`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Translation AI settings"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function saveTranslationAi(payload: TranslationAiPayload): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-ai`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save Translation AI settings"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function createTranslationAiProfile(name: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-ai/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create Translation AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function fetchTranslationAiProfile(profileId: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-ai/profiles/${encodeURIComponent(profileId)}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Translation AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function saveTranslationAiProfile(
  profileId: string,
  payload: TranslationAiPayload
): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-ai/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save Translation AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function patchTranslationAiProfile(
  profileId: string,
  patch: { name?: string; enabled?: boolean }
): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-ai/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to update Translation AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function renameTranslationAiProfile(
  profileId: string,
  name: string
): Promise<TranslationAiResponse> {
  return patchTranslationAiProfile(profileId, { name });
}

export async function setTranslationAiProfileEnabled(
  profileId: string,
  enabled: boolean
): Promise<TranslationAiResponse> {
  return patchTranslationAiProfile(profileId, { enabled });
}

export async function activateTranslationAiProfile(profileId: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-ai/profiles/${encodeURIComponent(profileId)}/activate`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to switch Translation AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function reorderTranslationAiProfiles(profileIds: string[]): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-ai/profiles/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_ids: profileIds })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to reorder Translation AI setups"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function deleteTranslationAiProfile(profileId: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/translation-ai/profiles/${encodeURIComponent(profileId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete Translation AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function testTranslationAi(
  payload: Partial<TranslationAiPayload> & { profile_id?: string }
): Promise<TranslationAiTestResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-ai/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to test Translation AI connection"));
  }
  return (await response.json()) as TranslationAiTestResponse;
}

export type TranslationAiModelsResponse = {
  ok: boolean;
  provider: string;
  models: string[];
  detail: string;
};

export async function listTranslationAiModels(payload: {
  provider: string;
  api_key?: string | null;
  clear_api_key?: boolean;
  base_url?: string | null;
  timeout_seconds?: number;
  profile_id?: string | null;
}): Promise<TranslationAiModelsResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/translation-ai/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to list Translation AI models"));
  }
  return (await response.json()) as TranslationAiModelsResponse;
}

export async function fetchCaptionPrompt(): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-prompt`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load caption prompt"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function saveCaptionPrompt(prompt: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-prompt`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save caption prompt"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function createCaptionPromptProfile(name: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-prompt/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create caption prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function fetchCaptionPromptProfile(profileId: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-prompt/profiles/${encodeURIComponent(profileId)}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load caption prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function saveCaptionPromptProfile(
  profileId: string,
  prompt: string
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-prompt/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt })
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save caption prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function renameCaptionPromptProfile(
  profileId: string,
  name: string
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-prompt/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to rename caption prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function activateCaptionPromptProfile(profileId: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-prompt/profiles/${encodeURIComponent(profileId)}/activate`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to switch caption prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function reorderCaptionPromptProfiles(
  profileIds: string[]
): Promise<TranslationPromptResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-prompt/profiles/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_ids: profileIds })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to reorder caption prompt setups"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function deleteCaptionPromptProfile(profileId: string): Promise<TranslationPromptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-prompt/profiles/${encodeURIComponent(profileId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete caption prompt setup"));
  }
  return (await response.json()) as TranslationPromptResponse;
}

export async function fetchCaptionAi(): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-ai`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Caption AI settings"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function saveCaptionAi(payload: TranslationAiPayload): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-ai`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save Caption AI settings"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function createCaptionAiProfile(name: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-ai/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create Caption AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function fetchCaptionAiProfile(profileId: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-ai/profiles/${encodeURIComponent(profileId)}`,
    { cache: "no-store" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load Caption AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function saveCaptionAiProfile(
  profileId: string,
  payload: TranslationAiPayload
): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-ai/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save Caption AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function patchCaptionAiProfile(
  profileId: string,
  patch: { name?: string; enabled?: boolean }
): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-ai/profiles/${encodeURIComponent(profileId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to update Caption AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function renameCaptionAiProfile(profileId: string, name: string): Promise<TranslationAiResponse> {
  return patchCaptionAiProfile(profileId, { name });
}

export async function setCaptionAiProfileEnabled(
  profileId: string,
  enabled: boolean
): Promise<TranslationAiResponse> {
  return patchCaptionAiProfile(profileId, { enabled });
}

export async function activateCaptionAiProfile(profileId: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-ai/profiles/${encodeURIComponent(profileId)}/activate`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to switch Caption AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function reorderCaptionAiProfiles(profileIds: string[]): Promise<TranslationAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-ai/profiles/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_ids: profileIds })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to reorder Caption AI setups"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function deleteCaptionAiProfile(profileId: string): Promise<TranslationAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/caption-ai/profiles/${encodeURIComponent(profileId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete Caption AI setup"));
  }
  return (await response.json()) as TranslationAiResponse;
}

export async function testCaptionAi(
  payload: Partial<TranslationAiPayload> & { profile_id?: string }
): Promise<TranslationAiTestResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-ai/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to test Caption AI connection"));
  }
  return (await response.json()) as TranslationAiTestResponse;
}

export async function listCaptionAiModels(payload: {
  provider?: string | null;
  api_key?: string | null;
  clear_api_key?: boolean;
  base_url?: string | null;
  timeout_seconds?: number;
  profile_id?: string | null;
}): Promise<TranslationAiModelsResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/caption-ai/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to list Caption AI models"));
  }
  return (await response.json()) as TranslationAiModelsResponse;
}

export type TtsAiCatalogVoice = {
  id: string;
  label: string;
};

export type TtsAiFieldCapabilities = {
  voice?: boolean;
  model?: boolean;
  styles?: boolean;
  api_key?: boolean;
  base_url?: boolean;
  local_backend?: boolean;
  cli_binary?: boolean;
};

export type TtsAiCatalog = {
  source: string;
  voices: TtsAiCatalogVoice[];
  styles: string[];
  models: string[];
  default_voice_id: string;
  warning: string;
  sample_rate?: number | null;
  backends?: string[];
  capabilities?: TtsAiFieldCapabilities | null;
};

export type TtsAiRuntime = {
  last_install?: {
    at?: string;
    ok?: boolean;
    command?: string;
    package?: string;
    detail?: string;
    already_satisfied?: boolean;
  } | null;
  last_probe?: {
    at?: string;
    ok?: boolean;
    provider?: string;
    detail?: string;
    catalog?: TtsAiCatalog | null;
  } | null;
};

export type TtsAiProfileSummary = {
  id: string;
  name: string;
  provider: string;
  enabled: boolean;
  voice_id?: string;
  speaking_rate?: number;
  language_code?: string;
  model_id?: string;
  api_key_set?: boolean;
  api_key_masked?: string;
  base_url?: string;
  timeout_seconds?: number;
  fallback_provider?: string;
  fallback_voice_id?: string;
  local_backend?: string;
  device?: string;
  cli_binary?: string;
  is_active?: boolean;
  runtime?: TtsAiRuntime;
};

export type TtsAiResponse = {
  enabled: boolean;
  provider: string;
  voice_id: string;
  speaking_rate: number;
  language_code: string;
  model_id: string;
  api_key_set: boolean;
  api_key_masked: string;
  base_url: string;
  timeout_seconds: number;
  fallback_provider: string;
  fallback_voice_id: string;
  local_backend: string;
  device: string;
  cli_binary: string;
  options_json: Record<string, unknown>;
  runtime?: TtsAiRuntime;
  live_import_ok?: boolean | null;
  source: string;
  updated?: boolean;
  active_profile_id?: string;
  active_profile_name?: string;
  profiles?: TtsAiProfileSummary[];
  focus_profile_id?: string | null;
};

export type TtsAiPayload = {
  enabled: boolean;
  provider: string;
  voice_id: string;
  speaking_rate: number;
  language_code: string;
  model_id: string;
  api_key?: string | null;
  clear_api_key?: boolean;
  base_url: string;
  timeout_seconds: number;
  fallback_provider: string;
  fallback_voice_id: string;
  local_backend: string;
  device: string;
  cli_binary: string;
  options_json: Record<string, unknown>;
};

export type TtsAiTestResponse = {
  ok: boolean;
  provider: string;
  detail: string;
  catalog?: TtsAiCatalog | null;
  runtime?: TtsAiRuntime | null;
};

export async function fetchTtsAi(): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load TTS AI settings"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function saveTtsAi(payload: TtsAiPayload): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save TTS AI settings"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function createTtsAiProfile(name: string): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to create TTS setup"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function fetchTtsAiProfile(profileId: string): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/profiles/${encodeURIComponent(profileId)}`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load TTS setup"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function saveTtsAiProfile(profileId: string, payload: TtsAiPayload): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/profiles/${encodeURIComponent(profileId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to save TTS setup"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function patchTtsAiProfile(
  profileId: string,
  patch: { name?: string; enabled?: boolean }
): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/profiles/${encodeURIComponent(profileId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to update TTS setup"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function renameTtsAiProfile(profileId: string, name: string): Promise<TtsAiResponse> {
  return patchTtsAiProfile(profileId, { name });
}

export async function setTtsAiProfileEnabled(profileId: string, enabled: boolean): Promise<TtsAiResponse> {
  return patchTtsAiProfile(profileId, { enabled });
}

export async function activateTtsAiProfile(profileId: string): Promise<TtsAiResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/ops/tts-ai/profiles/${encodeURIComponent(profileId)}/activate`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to switch TTS setup"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function reorderTtsAiProfiles(profileIds: string[]): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/profiles/reorder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_ids: profileIds })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to reorder TTS setups"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function deleteTtsAiProfile(profileId: string): Promise<TtsAiResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to delete TTS setup"));
  }
  return (await response.json()) as TtsAiResponse;
}

export async function testTtsAi(payload: Partial<TtsAiPayload> & { profile_id?: string }): Promise<TtsAiTestResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to test TTS AI connection"));
  }
  return (await response.json()) as TtsAiTestResponse;
}

export type TtsAiInstallPayload = {
  install_command?: string | null;
  package?: string | null;
  repo_url?: string | null;
  timeout_seconds?: number;
  provider?: string | null;
  profile_id?: string | null;
  force_reinstall?: boolean;
};

export type TtsAiInstallResponse = {
  ok: boolean;
  status?: string;
  detail: string;
  command: string;
  log_tail: string;
  already_satisfied?: boolean;
  probe_ok?: boolean | null;
  probe_detail?: string;
  provider?: string;
  catalog?: TtsAiCatalog | null;
  runtime?: TtsAiRuntime | null;
};

export async function installTtsAiPackage(payload: TtsAiInstallPayload): Promise<TtsAiInstallResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to install TTS package"));
  }
  return (await response.json()) as TtsAiInstallResponse;
}

export async function fetchTtsAiInstallStatus(): Promise<TtsAiInstallResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/install/status`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load TTS install status"));
  }
  return (await response.json()) as TtsAiInstallResponse;
}

export type TtsAiPreviewPayload = Partial<TtsAiPayload> & {
  text: string;
  max_chars?: number;
  profile_id?: string;
};

export type TtsAiPreviewResponse = {
  ok: boolean;
  status?: string;
  provider: string;
  detail: string;
  mime_type: string;
  duration_seconds: number;
  audio_base64: string;
  warnings: string[];
  text: string;
};

export async function previewTtsAiSpeech(payload: TtsAiPreviewPayload): Promise<TtsAiPreviewResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to preview TTS speech"));
  }
  return (await response.json()) as TtsAiPreviewResponse;
}

export async function fetchTtsAiPreviewStatus(): Promise<TtsAiPreviewResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/preview/status`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load TTS preview status"));
  }
  return (await response.json()) as TtsAiPreviewResponse;
}

export async function cancelTtsAiPreview(): Promise<TtsAiPreviewResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ops/tts-ai/preview/cancel`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to cancel TTS preview"));
  }
  return (await response.json()) as TtsAiPreviewResponse;
}

export async function fetchPipelineDashboard(): Promise<PipelineDashboardResponse> {
  const response = await apiFetch(`${API_BASE_URL}/pipeline-dashboard`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load pipeline dashboard"));
  }
  return (await response.json()) as PipelineDashboardResponse;
}

export async function applyCandidatePreset(filters: CandidateFilters): Promise<void> {
  if (!filters.presetName) return;
  const response = await apiFetch(`${API_BASE_URL}/candidates/filter/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      preset_name: filters.presetName,
      source_profile_id: filters.sourceProfileId || null,
      persist: true
    })
  });
  if (!response.ok) {
    throw new Error(`Failed to apply filter preset: ${response.status}`);
  }
}

export async function bulkUpdateCandidateStatus(
  candidateIds: string[],
  status: BulkActionStatus
): Promise<Candidate[]> {
  const response = await apiFetch(`${API_BASE_URL}/candidates/bulk-status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: candidateIds, status })
  });
  if (!response.ok) {
    throw new Error(`Failed to update candidates: ${response.status}`);
  }
  const payload = (await response.json()) as { candidates: Candidate[] };
  return payload.candidates;
}

export async function fetchTranscript(sourceVideoId: string): Promise<TranscriptListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/transcript`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load transcript: ${response.status}`);
  }
  return (await response.json()) as TranscriptListResponse;
}

export async function fetchTranslationDraft(sourceVideoId: string): Promise<TranslationDraftListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/translation-draft`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load translation draft: ${response.status}`);
  }
  return (await response.json()) as TranslationDraftListResponse;
}

export async function fetchAudioAnalysisSummary(sourceVideoId: string): Promise<AudioAnalysisSummaryResponse> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/audio-analysis-summary`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load audio analysis summary: ${response.status}`);
  }
  return (await response.json()) as AudioAnalysisSummaryResponse;
}

export async function saveTranscriptDraft(sourceVideoId: string, payload: TranscriptSavePayload): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/transcript-draft`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to save transcript draft: ${response.status}`);
  }
}

export async function mergeTranscriptSegments(
  sourceVideoId: string,
  leftTranscriptSegmentId: string,
  rightTranscriptSegmentId: string
): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/transcript-draft/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      left_transcript_segment_id: leftTranscriptSegmentId,
      right_transcript_segment_id: rightTranscriptSegmentId
    })
  });
  if (!response.ok) {
    throw new Error(`Failed to merge transcript segments: ${response.status}`);
  }
}

export async function splitTranscriptSegment(
  sourceVideoId: string,
  payload: {
    transcript_segment_id: string;
    split_ms: number;
    left_source_text: string;
    right_source_text: string;
    left_translated_text: string;
    right_translated_text: string;
  }
): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/transcript-draft/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to split transcript segment: ${response.status}`);
  }
}

export type AudioAnalysisCreateResponse = {
  job_id: string;
  status: string;
  source_video_id: string;
  translation_preset: TranslationPreset;
};

export type ApproveSourceTranscriptResponse = {
  source_video_id: string;
  approved_segments: number;
  dialogue_phase: string;
};

export async function approveSourceTranscript(
  sourceVideoId: string
): Promise<ApproveSourceTranscriptResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/source-videos/${sourceVideoId}/transcript-draft/approve-source`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to approve source transcript"));
  }
  return (await response.json()) as ApproveSourceTranscriptResponse;
}

export async function rerunTranslationDraft(
  sourceVideoId: string,
  translationPreset: TranslationPreset = "literal_safe"
): Promise<AudioAnalysisCreateResponse> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/translation-draft/rerun`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      translation_preset: translationPreset,
      force_refresh: true,
      require_source_approved: true
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to start literal translation"));
  }
  return (await response.json()) as AudioAnalysisCreateResponse;
}

export async function createAudioAnalysis(
  sourceVideoId: string,
  translationPreset: TranslationPreset = "literal_safe",
  forceRefresh = true,
  skipTranslation = true
): Promise<AudioAnalysisCreateResponse> {
  const response = await apiFetch(`${API_BASE_URL}/audio-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_video_id: sourceVideoId,
      translation_preset: translationPreset,
      force_refresh: forceRefresh,
      skip_translation: skipTranslation
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to start audio analysis"));
  }
  return (await response.json()) as AudioAnalysisCreateResponse;
}

export async function fetchLatestRender(sourceVideoId: string): Promise<RenderOutput | null> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/latest-render`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load latest render: ${response.status}`);
  }
  return (await response.json()) as RenderOutput | null;
}

export async function fetchRender(renderId: string): Promise<RenderOutput> {
  const response = await apiFetch(`${API_BASE_URL}/renders/${renderId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load render: ${response.status}`);
  }
  return (await response.json()) as RenderOutput;
}

export async function createRenderJob(sourceVideoId: string, forceRefresh = true): Promise<RenderCreateResponse> {
  const response = await apiFetch(`${API_BASE_URL}/renders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_video_id: sourceVideoId, render_mode: "final", force_refresh: forceRefresh })
  });
  if (!response.ok) {
    throw new Error(`Failed to create render job: ${response.status}`);
  }
  return (await response.json()) as RenderCreateResponse;
}

export async function approveRender(renderId: string): Promise<RenderOutput> {
  const response = await apiFetch(`${API_BASE_URL}/renders/${renderId}/approve`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to approve render: ${response.status}`);
  }
  return (await response.json()) as RenderOutput;
}

export async function markRenderPublishReady(renderId: string): Promise<RenderOutput> {
  const response = await apiFetch(`${API_BASE_URL}/renders/${renderId}/mark-publish-ready`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to mark publish-ready: ${response.status}`);
  }
  return (await response.json()) as RenderOutput;
}

export async function fetchSourceVideoAssetManifest(sourceVideoId: string): Promise<SourceVideoAssetManifest> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/asset-manifest`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load asset manifest: ${response.status}`);
  }
  return (await response.json()) as SourceVideoAssetManifest;
}

/** Ask the local API to open Explorer on the current SOURCE_VIDEO_RAW file (no path in response). */
export async function revealSourceVideoLocalAsset(sourceVideoId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${encodeURIComponent(sourceVideoId)}/reveal-local-asset`, {
    method: "POST"
  });
  if (!response.ok) {
    let message = `Failed to open downloaded media (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: { message?: string } | string };
      if (typeof body.detail === "string" && body.detail.trim()) message = body.detail;
      else if (body.detail && typeof body.detail === "object" && typeof body.detail.message === "string") {
        message = body.detail.message;
      }
    } catch {
      // keep status fallback
    }
    throw new Error(message);
  }
}

export function mediaAssetContentUrl(assetId: string): string {
  return `${API_BASE_URL}/media-assets/${assetId}/content`;
}

const DEFAULT_TTS_VOICE = {
  // Empty voice_id → API uses active Ops TTS profile (Preview parity) or env fallback.
  voice_id: "",
  language_code: "vi",
  speaking_rate: 1.0
} as const;

export async function createTtsJob(
  sourceVideoId: string,
  options: {
    voiceConfig?: Partial<{ voice_id: string; language_code: string; speaking_rate: number }>;
    forceRefresh?: boolean;
  } = {}
): Promise<TtsCreateResponse> {
  const voice_config = { ...DEFAULT_TTS_VOICE, ...options.voiceConfig };
  const response = await apiFetch(`${API_BASE_URL}/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_video_id: sourceVideoId,
      voice_config,
      force_refresh: options.forceRefresh ?? true
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to start TTS job"));
  }
  return (await response.json()) as TtsCreateResponse;
}

export async function createOcrJob(
  sourceVideoId: string,
  options: { forceRefresh?: boolean; cleanHardsub?: boolean } = {}
): Promise<OcrCreateResponse> {
  const response = await apiFetch(`${API_BASE_URL}/ocr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_video_id: sourceVideoId,
      force_refresh: options.forceRefresh ?? true,
      clean_hardsub: options.cleanHardsub ?? true,
      sample_fps: 1.0,
      hard_sub_band_ratio: 0.28
    })
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to start OCR job"));
  }
  return (await response.json()) as OcrCreateResponse;
}

export async function fetchOcrSummary(sourceVideoId: string): Promise<OcrSummaryResponse> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/ocr-summary`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load OCR summary"));
  }
  return (await response.json()) as OcrSummaryResponse;
}

export async function approveOcrVisual(sourceVideoId: string): Promise<OcrSummaryResponse> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/ocr-visual-approve`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to approve OCR visual"));
  }
  return (await response.json()) as OcrSummaryResponse;
}

export async function fetchTtsSummary(sourceVideoId: string): Promise<TtsSummaryResponse> {
  const response = await apiFetch(`${API_BASE_URL}/source-videos/${sourceVideoId}/tts-summary`, {
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await formatApiError(response, "Failed to load TTS summary"));
  }
  return (await response.json()) as TtsSummaryResponse;
}

/**
 * Browser <video>/<img> cannot attach Authorization headers. Protected media must be
 * fetched with apiFetch (Bearer), then played from a blob: object URL.
 */
export async function fetchMediaAssetObjectUrl(assetId: string): Promise<string> {
  const response = await apiFetch(mediaAssetContentUrl(assetId), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load media asset content: ${response.status}`);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export async function fetchPublishTargets(): Promise<PublishTarget[]> {
  const response = await apiFetch(`${API_BASE_URL}/publish-targets`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish targets: ${response.status}`);
  }
  return (await response.json()) as PublishTarget[];
}

export async function fetchPublishDrafts(sourceVideoId: string): Promise<PublishDraft[]> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts?source_video_id=${sourceVideoId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish drafts: ${response.status}`);
  }
  const payload = (await response.json()) as PublishDraftListResponse;
  return payload.drafts;
}

export async function fetchPublishDraft(draftId: string): Promise<PublishDraft> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish draft: ${response.status}`);
  }
  return (await response.json()) as PublishDraft;
}

export async function createPublishDraft(sourceVideoId: string, targetPlatform: PublishTargetPlatform): Promise<PublishDraft> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_video_id: sourceVideoId, target_platform: targetPlatform, generation_mode: "deterministic_v1" })
  });
  if (!response.ok) {
    throw new Error(`Failed to create publish draft: ${response.status}`);
  }
  return (await response.json()) as PublishDraft;
}

export async function updatePublishDraft(draftId: string, payload: Record<string, unknown>): Promise<PublishDraft> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to update publish draft: ${response.status}`);
  }
  return (await response.json()) as PublishDraft;
}

export async function schedulePublishDraft(draftId: string, payload: Record<string, unknown>): Promise<PublishDraft> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/schedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to schedule publish draft: ${response.status}`);
  }
  return (await response.json()) as PublishDraft;
}

export async function unschedulePublishDraft(draftId: string): Promise<PublishDraft> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/unschedule`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to unschedule publish draft: ${response.status}`);
  }
  return (await response.json()) as PublishDraft;
}

export async function markPublishDraftReady(draftId: string): Promise<PublishDraft> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/mark-ready`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to mark publish draft ready: ${response.status}`);
  }
  return (await response.json()) as PublishDraft;
}

export async function fetchPlatformAccounts(platform: PublishTargetPlatform = "FACEBOOK_REELS"): Promise<PlatformAccount[]> {
  const response = await apiFetch(`${API_BASE_URL}/platform-accounts?platform=${platform}&status=ACTIVE`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load platform accounts: ${response.status}`);
  }
  const payload = (await response.json()) as PlatformAccountListResponse;
  return payload.accounts;
}

export async function fetchAllPlatformAccounts(platform: PublishTargetPlatform = "FACEBOOK_REELS"): Promise<PlatformAccount[]> {
  const response = await apiFetch(`${API_BASE_URL}/platform-accounts?platform=${platform}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load platform accounts: ${response.status}`);
  }
  const payload = (await response.json()) as PlatformAccountListResponse;
  return payload.accounts;
}

export async function updatePlatformAccount(accountId: string, payload: Record<string, unknown>): Promise<PlatformAccount> {
  const response = await apiFetch(`${API_BASE_URL}/platform-accounts/${accountId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to update platform account: ${response.status}`);
  }
  return (await response.json()) as PlatformAccount;
}

export async function fetchPublishAttempts(draftId: string): Promise<PublishAttempt[]> {
  const response = await apiFetch(`${API_BASE_URL}/publish-attempts?publish_draft_id=${draftId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish attempts: ${response.status}`);
  }
  const payload = (await response.json()) as PublishAttemptListResponse;
  return payload.attempts;
}

export async function fetchPublishAttemptList(status?: PublishAttempt["status"], limit = 100): Promise<PublishAttempt[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));

  const response = await apiFetch(`${API_BASE_URL}/publish-attempts?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish attempts: ${response.status}`);
  }
  const payload = (await response.json()) as PublishAttemptListResponse;
  return payload.attempts;
}

export async function fetchPublishHistory(draftId: string): Promise<PublishHistoryResponse> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/publish-history`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish history: ${response.status}`);
  }
  return (await response.json()) as PublishHistoryResponse;
}

export async function publishDraftNow(draftId: string, platformAccountId: string): Promise<PublishAttempt> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ platform_account_id: platformAccountId, publish_mode: "publish_now" })
  });
  if (!response.ok) {
    throw new Error(`Failed to publish draft: ${response.status}`);
  }
  return (await response.json()) as PublishAttempt;
}

export async function refreshPublishAttemptStatus(attemptId: string): Promise<PublishAttempt> {
  const response = await apiFetch(`${API_BASE_URL}/publish-attempts/${attemptId}/refresh-status`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to refresh publish status: ${response.status}`);
  }
  return (await response.json()) as PublishAttempt;
}

export async function reconcilePublishDraft(draftId: string): Promise<PublishHistoryResponse> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/reconcile`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to reconcile publish draft: ${response.status}`);
  }
  await response.json();
  return fetchPublishHistory(draftId);
}

export async function fetchRiskSummary(targetType: RiskTargetType, targetId: string): Promise<RiskSummary> {
  const response = await apiFetch(`${API_BASE_URL}/targets/${targetType}/${targetId}/risk-summary`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load risk summary: ${response.status}`);
  }
  return (await response.json()) as RiskSummary;
}

export async function fetchRiskFlags(status?: RiskFlag["status"]): Promise<RiskFlag[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await apiFetch(`${API_BASE_URL}/risk-flags${suffix}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load risk flags: ${response.status}`);
  }
  const payload = (await response.json()) as { flags: RiskFlag[] };
  return payload.flags;
}

export async function runRiskScan(targetType: RiskTargetType, targetId: string): Promise<RiskSummary> {
  const response = await apiFetch(`${API_BASE_URL}/risk-scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_type: targetType, target_id: targetId })
  });
  if (!response.ok) {
    throw new Error(`Failed to run risk scan: ${response.status}`);
  }
  return (await response.json()) as RiskSummary;
}

export async function updateRiskFlagStatus(flagId: string, action: "acknowledge" | "resolve" | "waive", note?: string): Promise<RiskFlag> {
  const response = await apiFetch(`${API_BASE_URL}/risk-flags/${flagId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: note ?? null })
  });
  if (!response.ok) {
    throw new Error(`Failed to update risk flag: ${response.status}`);
  }
  return (await response.json()) as RiskFlag;
}

export async function createRiskDecision(
  targetType: RiskTargetType,
  targetId: string,
  decisionType: OperatorRiskDecisionType,
  note?: string
): Promise<RiskSummary> {
  const response = await apiFetch(`${API_BASE_URL}/risk-decisions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_type: targetType, target_id: targetId, decision_type: decisionType, note: note ?? null })
  });
  if (!response.ok) {
    throw new Error(`Failed to create risk decision: ${response.status}`);
  }
  return (await response.json()) as RiskSummary;
}

export async function fetchPublishHealthDashboard(window: AnalyticsWindow = "last_7_days"): Promise<PublishHealthDashboard> {
  const response = await apiFetch(`${API_BASE_URL}/analytics/publish-health?window=${window}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish health dashboard: ${response.status}`);
  }
  return (await response.json()) as PublishHealthDashboard;
}

export async function submitOperatorFeedback(payload: OperatorFeedbackPayload): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/operator-feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to save operator feedback: ${response.status}`);
  }
}

export async function fetchPublishControlQueue(): Promise<PublishControlQueue> {
  const response = await apiFetch(`${API_BASE_URL}/publish-control/queue`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load publish control queue: ${response.status}`);
  }
  return (await response.json()) as PublishControlQueue;
}

export async function fetchRoutingRecommendation(draftId: string): Promise<RoutingRecommendation> {
  const response = await apiFetch(`${API_BASE_URL}/publish-routing/recommendations?publish_draft_id=${draftId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load routing recommendation: ${response.status}`);
  }
  return (await response.json()) as RoutingRecommendation;
}

export async function assignPublishDraft(draftId: string, payload: AssignDraftPayload): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/assign-account`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to assign publish draft: ${response.status}`);
  }
}

export async function unassignPublishDraft(draftId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/${draftId}/unassign-account`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Failed to unassign publish draft: ${response.status}`);
  }
}

export async function bulkAssignPublishDrafts(payload: BulkAssignPayload): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/publish-drafts/bulk-assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Failed to bulk assign publish drafts: ${response.status}`);
  }
}

export async function fetchRoutingRules(): Promise<RoutingRuleListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/routing-rules?platform=FACEBOOK_REELS`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load routing rules: ${response.status}`);
  }
  return (await response.json()) as RoutingRuleListResponse;
}

export async function fetchOptimizationDashboard(): Promise<OptimizationDashboard> {
  const response = await apiFetch(`${API_BASE_URL}/optimization/dashboard-snapshot`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load optimization dashboard: ${response.status}`);
  }
  return (await response.json()) as OptimizationDashboard;
}

export async function fetchOutcomeScore(draftId: string): Promise<OutcomeScore> {
  const response = await apiFetch(`${API_BASE_URL}/optimization/outcome-score/${draftId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load outcome score: ${response.status}`);
  }
  return (await response.json()) as OutcomeScore;
}

export async function fetchOptimizationRoutingHints(draftId: string): Promise<RoutingHints> {
  const response = await apiFetch(`${API_BASE_URL}/optimization/routing-hints?publish_draft_id=${draftId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load optimization routing hints: ${response.status}`);
  }
  return (await response.json()) as RoutingHints;
}

export async function fetchOptimizationSchedulingHints(draftId: string): Promise<SchedulingHints> {
  const response = await apiFetch(`${API_BASE_URL}/optimization/scheduling-hints?publish_draft_id=${draftId}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load scheduling hints: ${response.status}`);
  }
  return (await response.json()) as SchedulingHints;
}

async function formatApiError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json() as {
      detail?: string | { message?: string; code?: string; stage?: string; diagnostics_id?: string };
    };
    if (typeof payload.detail === "string") return `${fallback}: ${payload.detail}`;
    if (payload.detail?.message) {
      const suffix: string[] = [];
      if (payload.detail.code) suffix.push(`code: ${payload.detail.code}`);
      if (payload.detail.stage) suffix.push(`stage: ${payload.detail.stage}`);
      if (payload.detail.diagnostics_id) suffix.push(`diagnostics: ${payload.detail.diagnostics_id}`);
      return suffix.length > 0
        ? `${fallback}: ${payload.detail.message} (${suffix.join(", ")})`
        : `${fallback}: ${payload.detail.message}`;
    }
  } catch {
    // Fall through to status-based message.
  }
  return `${fallback}: ${response.status}`;
}
