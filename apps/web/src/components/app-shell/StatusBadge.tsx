import { humanizeStatus } from "../../lib/statusLabels";

type Tone = "good" | "warn" | "danger" | "muted";

export function StatusBadge({ label, tone = "muted" }: { label: string; tone?: Tone }) {
  return <span className={`app-status-badge ${tone}`}>{humanizeStatus(label)}</span>;
}

export function HealthBadge({ label, tone = "muted" }: { label: string; tone?: Tone }) {
  return <StatusBadge label={label} tone={tone} />;
}
