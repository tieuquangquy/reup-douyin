export function isAnalyzeJobTerminal(status: string): boolean {
  const normalized = status.toUpperCase();
  return normalized === "COMPLETED" || normalized === "SUCCEEDED" || normalized === "FAILED" || normalized === "CANCELLED";
}

export function isAnalyzeJobSuccessful(status: string): boolean {
  const normalized = status.toUpperCase();
  return normalized === "COMPLETED" || normalized === "SUCCEEDED";
}

export type AnalyzeJobPollResult =
  | { outcome: "success"; status: string }
  | { outcome: "failed"; status: string; errorMessage: string | null }
  | { outcome: "timeout"; status: string | null };

/**
 * Poll until ANALYZE_AUDIO reaches a terminal status or the attempt budget is exhausted.
 * Inject `fetchStatus` / `sleep` for deterministic tests.
 */
export async function pollAnalyzeJobUntilSettled(options: {
  fetchStatus: () => Promise<{ status: string; error_message?: string | null; error_code?: string | null }>;
  sleep?: (ms: number) => Promise<void>;
  intervalMs?: number;
  maxAttempts?: number;
}): Promise<AnalyzeJobPollResult> {
  const sleep = options.sleep ?? ((ms: number) => new Promise((resolve) => setTimeout(resolve, ms)));
  const intervalMs = options.intervalMs ?? 2000;
  const maxAttempts = options.maxAttempts ?? 180; // ~6 minutes at 2s
  let lastStatus: string | null = null;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const snapshot = await options.fetchStatus();
    lastStatus = snapshot.status;
    if (isAnalyzeJobSuccessful(snapshot.status)) {
      return { outcome: "success", status: snapshot.status };
    }
    if (isAnalyzeJobTerminal(snapshot.status)) {
      return {
        outcome: "failed",
        status: snapshot.status,
        errorMessage: snapshot.error_message ?? snapshot.error_code ?? snapshot.status
      };
    }
    if (attempt + 1 < maxAttempts) {
      await sleep(intervalMs);
    }
  }

  return { outcome: "timeout", status: lastStatus };
}
