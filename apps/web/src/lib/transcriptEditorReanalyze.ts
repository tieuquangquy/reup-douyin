export function isAnalyzeJobTerminal(status: string): boolean {
  const normalized = status.toUpperCase();
  return (
    normalized === "COMPLETED" ||
    normalized === "SUCCEEDED" ||
    normalized === "FAILED" ||
    normalized === "CANCELLED"
  );
}

export function isAnalyzeJobSuccessful(status: string): boolean {
  const normalized = status.toUpperCase();
  return normalized === "COMPLETED" || normalized === "SUCCEEDED";
}

export function isAnalyzeJobCancelled(status: string): boolean {
  return status.toUpperCase() === "CANCELLED";
}

export type AnalyzeJobPollSnapshot = {
  status: string;
  progress_percent?: number | null;
  error_message?: string | null;
  error_code?: string | null;
};

export type AnalyzeJobPollResult =
  | { outcome: "success"; status: string }
  | { outcome: "failed"; status: string; errorMessage: string | null }
  | { outcome: "cancelled"; status: string }
  | { outcome: "timeout"; status: string | null };

/**
 * Poll until ANALYZE_AUDIO / TTS / translation reaches a terminal status or the attempt budget is exhausted.
 * Inject `fetchStatus` / `sleep` for deterministic tests.
 */
export async function pollAnalyzeJobUntilSettled(options: {
  fetchStatus: () => Promise<AnalyzeJobPollSnapshot>;
  onSnapshot?: (snapshot: AnalyzeJobPollSnapshot) => void;
  shouldStop?: () => boolean;
  sleep?: (ms: number) => Promise<void>;
  intervalMs?: number;
  maxAttempts?: number;
}): Promise<AnalyzeJobPollResult> {
  const sleep = options.sleep ?? ((ms: number) => new Promise((resolve) => setTimeout(resolve, ms)));
  const intervalMs = options.intervalMs ?? 2000;
  const maxAttempts = options.maxAttempts ?? 180; // ~6 minutes at 2s
  let lastStatus: string | null = null;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.shouldStop?.()) {
      return { outcome: "cancelled", status: lastStatus ?? "CANCELLED" };
    }
    const snapshot = await options.fetchStatus();
    lastStatus = snapshot.status;
    options.onSnapshot?.(snapshot);
    if (isAnalyzeJobSuccessful(snapshot.status)) {
      return { outcome: "success", status: snapshot.status };
    }
    if (isAnalyzeJobCancelled(snapshot.status)) {
      return { outcome: "cancelled", status: snapshot.status };
    }
    if (isAnalyzeJobTerminal(snapshot.status)) {
      return {
        outcome: "failed",
        status: snapshot.status,
        errorMessage: snapshot.error_message ?? snapshot.error_code ?? snapshot.status
      };
    }
    if (options.shouldStop?.()) {
      return { outcome: "cancelled", status: lastStatus ?? "CANCELLED" };
    }
    if (attempt + 1 < maxAttempts) {
      await sleep(intervalMs);
    }
  }

  return { outcome: "timeout", status: lastStatus };
}
