import {
  formatConnectionTestDetail,
  type ConnectionTestResult
} from "./opsTranslationAiFormat";

export type TtsProbeSuccessView = {
  title: string;
  message: string;
  provider: string;
};

/**
 * Turn raw TTS probe dumps like ``auto → vieneu available`` into operator copy.
 * Test success means the machine probe passed — not that the setup form is finished.
 */
export function formatTtsProbeSuccess(
  result: ConnectionTestResult,
  labels: {
    passed: string;
    autoVieneu: string;
    autoEdge: string;
    generic: string;
  }
): TtsProbeSuccessView {
  const provider = result.provider.trim() || "unknown";
  const detail = (result.detail || "").trim();
  let message = labels.generic;
  let chip = provider;
  if (/vieneu available/i.test(detail) || /auto\s*→\s*vieneu/i.test(detail)) {
    message = labels.autoVieneu;
    if (provider === "auto") chip = "auto → vieneu";
  } else if (/edge-tts available/i.test(detail) || /auto\s*→\s*edge/i.test(detail)) {
    message = labels.autoEdge;
    if (provider === "auto") chip = "auto → edge";
  } else {
    const cleaned = formatConnectionTestDetail(detail);
    if (cleaned) message = cleaned;
  }
  return { title: labels.passed, message, provider: chip };
}
