import assert from "node:assert/strict";
import {
  EXTENSION_BUILD_COMMAND,
  EXTENSION_DIST_PATH,
  resolveDouyinExtensionDownloadState
} from "../lib/douyinExtensionInstall";
import type { DouyinExtensionStatusResponse } from "../types/douyin-extension-setup";

const baseStatus: DouyinExtensionStatusResponse = {
  status: "not_installed_or_not_connected",
  connected: false,
  install_id: null,
  extension_id: null,
  extension_version: null,
  browser_family: null,
  api_base_url: null,
  last_seen_at: null,
  stale_after_seconds: 120,
  backend_checked_at: "2026-04-26T17:00:00Z",
  backend_expected_extension_version: "0.1.0",
  backend_supported_extension_versions: ["0.1.0"],
  version_status: "unknown",
  compatible: false,
  recommended_next_action: "build_extension",
  recommended_next_action_label: "Build the extension.",
  operator_message: "Build the extension before installing.",
  download_available: false,
  download_url: "/douyin-extension/download",
  manual_install_required: true,
  chrome_extensions_url: "chrome://extensions",
  edge_extensions_url: "edge://extensions"
};

const loading = resolveDouyinExtensionDownloadState(null, "http://127.0.0.1:8000/douyin-extension/download");
assert.equal(loading.kind, "loading");
assert.equal(loading.href, null);
assert.match(loading.label, /Checking download availability/);

const unavailable = resolveDouyinExtensionDownloadState(baseStatus, "http://127.0.0.1:8000/douyin-extension/download");
assert.equal(unavailable.kind, "unavailable");
assert.equal(unavailable.href, null);
assert.match(unavailable.label, /Download unavailable/);
assert.match(unavailable.description, new RegExp(EXTENSION_BUILD_COMMAND.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
assert.match(unavailable.description, new RegExp(EXTENSION_DIST_PATH.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

const available = resolveDouyinExtensionDownloadState(
  { ...baseStatus, download_available: true, recommended_next_action: "download_extension" },
  "http://127.0.0.1:8000/douyin-extension/download"
);
assert.equal(available.kind, "available");
assert.equal(available.href, "http://127.0.0.1:8000/douyin-extension/download");
assert.equal(available.label, "Download extension");

console.log("douyin-extension install state tests passed");
