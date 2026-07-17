export type DouyinExtensionSetupStatus =
  | "not_installed_or_not_connected"
  | "installed_not_connected"
  | "connected"
  | "version_mismatch"
  | "backend_unreachable_from_extension"
  | "stale_connection";

export type DouyinExtensionBrowserFamily = "chrome" | "edge" | "chromium" | "unknown";

export type DouyinExtensionVersionStatus = "compatible" | "version_mismatch" | "unknown";

export type DouyinExtensionRecommendedAction =
  | "download_extension"
  | "build_extension"
  | "install_extension_manually"
  | "open_extension_and_check_connection"
  | "refresh_setup_page"
  | "update_extension"
  | "open_douyin_and_capture"
  | "check_backend_url";

export type DouyinExtensionStatusResponse = {
  status: DouyinExtensionSetupStatus;
  connected: boolean;
  install_id: string | null;
  extension_id: string | null;
  extension_version: string | null;
  browser_family: DouyinExtensionBrowserFamily | null;
  api_base_url: string | null;
  last_seen_at: string | null;
  stale_after_seconds: number;
  backend_checked_at: string;
  backend_expected_extension_version: string;
  backend_supported_extension_versions: string[];
  version_status: DouyinExtensionVersionStatus;
  compatible: boolean;
  recommended_next_action: DouyinExtensionRecommendedAction;
  recommended_next_action_label: string;
  operator_message: string;
  download_available: boolean;
  download_url: string;
  manual_install_required: boolean;
  chrome_extensions_url: string;
  edge_extensions_url: string;
};
