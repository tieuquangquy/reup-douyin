import { ExtensionDirectExecutionError, projectDirectExecutionError, type ExtensionDirectExecutionErrorCode } from "./popupTransport.js";

export type PopupErrorCategory =
  | "backend_timeout"
  | "backend_unreachable"
  | "backend_error"
  | "no_active_tab"
  | "unsupported_tab"
  | "challenge_page"
  | "login_page"
  | "detect_failed"
  | "capture_failed"
  | "direct_execution_failed";

export type PopupActionName = "check_connection" | "detect_current_page" | "capture_current_page";

export type PopupActionTone = "good" | "error" | "";

export type PopupFriendlyError = {
  category: PopupErrorCategory;
  message: string;
  nextAction: string;
};

export type PopupActionState = {
  loading: boolean;
  lastAction: PopupActionName | null;
  lastErrorCategory: PopupErrorCategory | null;
};

export type PopupActionRenderer = {
  setLoading(loading: boolean): void;
  renderError(error: PopupFriendlyError): void;
};

export class PopupActionError extends Error {
  readonly category: PopupErrorCategory;
  readonly nextAction: string;

  constructor(category: PopupErrorCategory, message: string, nextAction: string) {
    super(message);
    this.name = "PopupActionError";
    this.category = category;
    this.nextAction = nextAction;
  }
}

export const POPUP_ERROR_MESSAGES: Record<PopupErrorCategory, { message: string; nextAction: string }> = {
  backend_timeout: {
    message: "Backend did not respond before the timeout. Confirm the API is running and try again.",
    nextAction: "Start or restart the local API, then check extension connection again."
  },
  backend_unreachable: {
    message: "Backend is unreachable from the extension popup. Check the API URL and local API process.",
    nextAction: "Confirm the API base URL, usually http://127.0.0.1:8000, then retry."
  },
  backend_error: {
    message: "Backend returned an error while handling the popup action.",
    nextAction: "Review the backend message, then retry after correcting the issue."
  },
  no_active_tab: {
    message: "No active tab is available. Open a supported Douyin tab and try again.",
    nextAction: "Open a Douyin tab in the current window."
  },
  unsupported_tab: {
    message: "The active tab is not a supported Douyin page.",
    nextAction: "Open https://www.douyin.com on a profile, feed, or video page."
  },
  challenge_page: {
    message: "Douyin is showing a challenge page.",
    nextAction: "Solve the challenge in the browser, refresh the page, and retry."
  },
  login_page: {
    message: "Douyin is asking for login.",
    nextAction: "Log in in the browser, refresh the page, and retry."
  },
  detect_failed: {
    message: "Could not detect the current Douyin page.",
    nextAction: "Refresh the tab and retry detection."
  },
  capture_failed: {
    message: "Could not capture the current Douyin page.",
    nextAction: "Refresh the tab, confirm it is capturable, and retry capture."
  },
  direct_execution_failed: {
    message: "Could not execute the Douyin detector in this tab.",
    nextAction: "Reconnect Douyin Tab. If reconnect fails, reload the extension, then hard refresh the Douyin tab."
  }
};

const DIRECT_ERROR_CATEGORY_MAP: Record<ExtensionDirectExecutionErrorCode, PopupErrorCategory> = {
  no_active_tab: "no_active_tab",
  unsupported_tab: "unsupported_tab",
  unsupported_douyin_page: "unsupported_tab",
  login_page: "login_page",
  challenge_page: "challenge_page",
  capture_not_supported: "capture_failed",
  direct_execution_failed: "direct_execution_failed"
};

export async function runPopupAction(
  actionName: PopupActionName,
  renderer: PopupActionRenderer,
  action: () => Promise<void>,
  state: PopupActionState = createPopupActionState()
): Promise<PopupActionState> {
  state.loading = true;
  state.lastAction = actionName;
  state.lastErrorCategory = null;
  renderer.setLoading(true);
  try {
    await action();
  } catch (error) {
    const friendly = projectPopupActionError(error, actionName);
    state.lastErrorCategory = friendly.category;
    renderer.renderError(friendly);
  } finally {
    state.loading = false;
    renderer.setLoading(false);
  }
  return state;
}

export function createPopupActionState(): PopupActionState {
  return {
    loading: false,
    lastAction: null,
    lastErrorCategory: null
  };
}

export function projectPopupActionError(error: unknown, actionName: PopupActionName): PopupFriendlyError {
  if (error instanceof PopupActionError) {
    return {
      category: error.category,
      message: error.message,
      nextAction: error.nextAction
    };
  }

  if (error instanceof DOMException && error.name === "AbortError") return popupFriendlyError("backend_timeout");

  if (error instanceof TypeError) return popupFriendlyError("backend_unreachable");

  if (error instanceof ExtensionDirectExecutionError) {
    const direct = projectDirectExecutionError(error);
    return {
      category: DIRECT_ERROR_CATEGORY_MAP[direct.code],
      message: direct.message,
      nextAction: POPUP_ERROR_MESSAGES[DIRECT_ERROR_CATEGORY_MAP[direct.code]].nextAction
    };
  }

  const message = error instanceof Error ? error.message : "Popup action failed.";
  if (/timeout|timed out/i.test(message)) {
    return actionName === "check_connection" ? popupFriendlyError("backend_timeout") : popupFriendlyError("direct_execution_failed");
  }
  if (/fetch|network|failed to fetch/i.test(message)) return popupFriendlyError("backend_unreachable");

  if (actionName === "detect_current_page") return { ...popupFriendlyError("detect_failed"), message };
  if (actionName === "capture_current_page") return { ...popupFriendlyError("capture_failed"), message };
  return { ...popupFriendlyError("backend_error"), message };
}

export function popupFriendlyError(category: PopupErrorCategory, message?: string): PopupFriendlyError {
  const fallback = POPUP_ERROR_MESSAGES[category];
  return {
    category,
    message: message || fallback.message,
    nextAction: fallback.nextAction
  };
}

export function backendHttpError(message: string): PopupActionError {
  return new PopupActionError("backend_error", message, POPUP_ERROR_MESSAGES.backend_error.nextAction);
}

export function backendTimeoutError(): PopupActionError {
  return new PopupActionError("backend_timeout", POPUP_ERROR_MESSAGES.backend_timeout.message, POPUP_ERROR_MESSAGES.backend_timeout.nextAction);
}

export function withTimeout<T>(operation: Promise<T>, timeoutMs: number, onTimeout: () => Error): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = setTimeout(() => reject(onTimeout()), timeoutMs);
  });

  return Promise.race([operation, timeout]).finally(() => {
    if (timeoutId) clearTimeout(timeoutId);
  });
}
