export function isPublicHttpsUrl(value: string | null | undefined): boolean {
  try {
    const url = new URL(value ?? "");
    const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    if (
      url.protocol !== "https:"
      || !hostname
      || hostname === "localhost"
      || hostname === "::1"
      || hostname.endsWith(".local")
    ) return false;
    const ipv4 = hostname.split(".").map(Number);
    if (ipv4.length === 4 && ipv4.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)) {
      return !(
        ipv4[0] === 10
        || ipv4[0] === 127
        || (ipv4[0] === 169 && ipv4[1] === 254)
        || (ipv4[0] === 172 && ipv4[1] >= 16 && ipv4[1] <= 31)
        || (ipv4[0] === 192 && ipv4[1] === 168)
      );
    }
    return true;
  } catch {
    return false;
  }
}
