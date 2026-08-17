export type HandoffCargoRow = { key: string; label: string; value: string };
export type HandoffCargoGroupId = "media" | "refs";
export type HandoffCargoGroup = { id: HandoffCargoGroupId; rows: HandoffCargoRow[] };

const STUB_KEYS = new Set(["target_platform", "export_package_id"]);
const MEDIA_KEYS = new Set(["source_video_id", "render_output_id", "quality_manual_export_archive"]);
const SHORT_LABELS: Record<string, string> = {
  source_video_id: "Video",
  render_output_id: "Render",
  quality_manual_export_archive: "Archive",
  reup_queue_item_id: "Queue",
  video_candidate_id: "Candidate",
  item_count: "Items"
};

export function buildHandoffCargo(payload: Record<string, unknown> | null): HandoffCargoGroup[] {
  if (!payload) return [];

  const media: HandoffCargoRow[] = [];
  const refs: HandoffCargoRow[] = [];

  function addRow(keyName: string, path: string, value: unknown, labelPrefix = "") {
    if (STUB_KEYS.has(keyName)) return;
    const text = scalarText(value);
    if (text === null) return;
    if (keyName === "item_count" && Number(text) <= 1) return;
    const row = { key: path, label: `${labelPrefix}${SHORT_LABELS[keyName] ?? prettyKey(keyName)}`, value: text };
    if (MEDIA_KEYS.has(keyName)) media.push(row);
    else refs.push(row);
  }

  for (const [key, value] of Object.entries(payload)) {
    if (STUB_KEYS.has(key)) continue;
    const scalar = scalarText(value);
    if (scalar !== null) {
      addRow(key, key, value);
      continue;
    }
    if (!Array.isArray(value)) continue;
    value.forEach((entry, index) => {
      const entryText = scalarText(entry);
      if (entryText !== null) {
        addRow(key, `${key}.${index}`, entry);
        return;
      }
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) return;
      for (const [innerKey, innerValue] of Object.entries(entry as Record<string, unknown>)) {
        addRow(innerKey, `${key}.${index}.${innerKey}`, innerValue, value.length > 1 ? `${index + 1} · ` : "");
      }
    });
  }

  return [
    { id: "media" as const, rows: media },
    { id: "refs" as const, rows: refs }
  ].filter((group) => group.rows.length > 0);
}

function prettyKey(key: string): string {
  return key.replace(/_/g, " ");
}

function scalarText(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}
