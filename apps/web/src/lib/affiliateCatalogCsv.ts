import type { AffiliateAvailability, AffiliatePlatform, AffiliateProductInput } from "../types/affiliate";


function parseCsvRows(input: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < input.length; index += 1) {
    const char = input[index];
    const next = input[index + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell.trim());
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  return rows;
}


function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.replaceAll("%", "").replaceAll(" ", ""));
  return Number.isFinite(parsed) ? parsed : null;
}


function platform(value: string): AffiliatePlatform {
  const normalized = value.trim().toUpperCase();
  return ["FACEBOOK", "TIKTOK_SHOP", "SHOPEE"].includes(normalized)
    ? normalized as AffiliatePlatform
    : "OTHER";
}


function availability(value: string): AffiliateAvailability {
  const normalized = value.trim().toUpperCase();
  return normalized === "IN_STOCK" || normalized === "OUT_OF_STOCK" ? normalized : "UNKNOWN";
}


export type AffiliateCatalogCsvRow = AffiliateProductInput & { topic_codes: string[] };


export function parseAffiliateCatalogCsv(input: string): AffiliateCatalogCsvRow[] {
  const rows = parseCsvRows(input);
  if (rows.length < 2) return [];
  const headers = rows[0].map((header) => header.trim().toLowerCase());
  const index = (name: string) => headers.indexOf(name);
  const value = (row: string[], name: string) => {
    const position = index(name);
    return position >= 0 ? row[position] ?? "" : "";
  };
  return rows.slice(1).map((row) => ({
    platform: platform(value(row, "platform")),
    external_product_id: value(row, "external_product_id") || null,
    merchant_name: value(row, "merchant_name") || null,
    name: value(row, "name"),
    description: value(row, "description") || null,
    image_url: value(row, "image_url") || null,
    product_url: value(row, "product_url") || null,
    affiliate_url: value(row, "affiliate_url"),
    currency_code: value(row, "currency_code") || "VND",
    price_amount: numberOrNull(value(row, "price_amount")),
    commission_rate_percent: numberOrNull(value(row, "commission_rate_percent")),
    commission_amount: numberOrNull(value(row, "commission_amount")),
    availability_status: availability(value(row, "availability_status")),
    keywords: value(row, "keywords").split("|").map((item) => item.trim()).filter(Boolean),
    supported_platforms: value(row, "supported_platforms").split("|").map((item) => item.trim()).filter(Boolean),
    topic_codes: value(row, "topic_codes").split("|").map((item) => item.trim().toUpperCase()).filter(Boolean),
    topic_ids: [],
    is_active: value(row, "is_active").toLowerCase() !== "false",
  }));
}
