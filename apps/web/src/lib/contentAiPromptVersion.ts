/** Display helper for Content AI prompt version keys (no live I/O). */
export function formatContentAiPromptVersion(version: string): string {
  const raw = version.trim();
  const stamped = raw.match(/^CLASSIFICATION_PROMPT_(\d{8})(\d{6})$/);
  if (stamped) {
    const day = stamped[1];
    const time = stamped[2];
    return `${day.slice(0, 4)}-${day.slice(4, 6)}-${day.slice(6, 8)} · ${time.slice(0, 2)}:${time.slice(2, 4)}`;
  }
  const labeled = raw.match(/^CLASSIFICATION_PROMPT_(.+)$/);
  if (labeled) return labeled[1].replace(/_/g, ".");
  return raw;
}
