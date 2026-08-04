import type { ContentClassification } from "../types/content-intelligence";


export type ClassificationSourceKind = "AI" | "LOCAL" | "AI_FALLBACK";


export type ClassificationSourcePresentation = {
  kind: ClassificationSourceKind;
  provider: string;
  model: string | null;
  promptVersion: string | null;
  networkUsed: boolean;
};


function metadataText(classification: ContentClassification, key: string): string | null {
  const value = classification.metadata_json?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}


export function getClassificationSourcePresentation(
  classification: ContentClassification,
): ClassificationSourcePresentation {
  const provider = metadataText(classification, "provider") ?? (
    classification.classifier_version.startsWith("LOCAL_") ? "LOCAL_KEYWORD" : "UNKNOWN"
  );
  const networkUsed = classification.metadata_json?.network_used === true;
  const fallbackFrom = metadataText(classification, "fallback_from");
  const kind: ClassificationSourceKind = fallbackFrom === "AI"
    ? "AI_FALLBACK"
    : networkUsed
      ? "AI"
      : "LOCAL";
  return {
    kind,
    provider,
    model: metadataText(classification, "model"),
    promptVersion: metadataText(classification, "prompt_version"),
    networkUsed,
  };
}


export function classificationSourceTitle(source: ClassificationSourcePresentation): string {
  return [source.provider, source.model, source.promptVersion].filter(Boolean).join(" · ");
}
