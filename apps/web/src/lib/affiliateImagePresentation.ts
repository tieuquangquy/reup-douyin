const AFFILIATE_ASSET_PATH = /^\/(?:api\/)?public\/affiliate-product-images\/[0-9a-f-]+$/i;


/**
 * Render app-owned images through the current web origin.
 *
 * The persisted URL may use a public tunnel so Meta can fetch it. A tunnel can
 * later change or go offline, but the operator UI should still preview the
 * local asset through the Next.js `/api` rewrite.
 */
export function affiliateImagePreviewUrl(imageUrl: string): string {
  const cleaned = imageUrl.trim();
  if (!cleaned) return cleaned;
  try {
    const parsed = new URL(cleaned, "http://local.invalid");
    if (!AFFILIATE_ASSET_PATH.test(parsed.pathname)) return cleaned;
    return parsed.pathname.startsWith("/api/") ? parsed.pathname : `/api${parsed.pathname}`;
  } catch {
    return cleaned;
  }
}
