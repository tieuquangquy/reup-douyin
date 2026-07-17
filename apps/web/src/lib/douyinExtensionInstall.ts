import type { DouyinExtensionStatusResponse } from "../types/douyin-extension-setup";

export type DouyinExtensionDownloadState =
  | {
      kind: "loading";
      label: string;
      description: string;
      href: null;
    }
  | {
      kind: "available";
      label: string;
      description: string;
      href: string;
    }
  | {
      kind: "unavailable";
      label: string;
      description: string;
      href: null;
    };

export const EXTENSION_BUILD_COMMAND = "npm run extension:build";
export const EXTENSION_DIST_PATH = "apps/extension-douyin-capture/dist";

export function resolveDouyinExtensionDownloadState(
  status: DouyinExtensionStatusResponse | null,
  downloadUrl: string
): DouyinExtensionDownloadState {
  if (!status) {
    return {
      kind: "loading",
      label: "Checking download availability...",
      description: "The setup page is checking whether a built extension ZIP is available.",
      href: null
    };
  }

  if (status.download_available) {
    return {
      kind: "available",
      label: "Download extension",
      description: "A built extension artifact is available. Download the ZIP, extract it, then load the extracted folder manually.",
      href: downloadUrl
    };
  }

  return {
    kind: "unavailable",
    label: "Download unavailable — use Load unpacked from dist",
    description: `No downloadable ZIP is available yet. Run ${EXTENSION_BUILD_COMMAND}, then load ${EXTENSION_DIST_PATH} with the browser Load unpacked flow.`,
    href: null
  };
}
