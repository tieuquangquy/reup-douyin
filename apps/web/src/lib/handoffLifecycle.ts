export type HandoffLifecycleTone = "done" | "pending" | "attention" | "muted";

export type HandoffLifecycleStep = {
  key: string;
  label: string;
  at: string | null;
  tone: HandoffLifecycleTone;
};

export function mergeLifecycleByMinute(
  steps: HandoffLifecycleStep[],
  format: (iso: string) => string
): HandoffLifecycleStep[] {
  const merged: HandoffLifecycleStep[] = [];
  for (const step of steps) {
    const prev = merged[merged.length - 1];
    if (prev?.at && step.at && format(prev.at) === format(step.at)) {
      prev.key = `${prev.key}+${step.key}`;
      prev.label = `${prev.label} · ${step.label}`;
      continue;
    }
    merged.push({ ...step });
  }
  return merged;
}
