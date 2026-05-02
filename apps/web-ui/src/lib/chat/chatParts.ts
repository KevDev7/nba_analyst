import { textArtifactsOrFallback } from "$lib/artifacts/text";
import type { Artifact, ChartArtifact, TableArtifact, TextArtifact } from "$lib/artifacts/types";
import { isChartArtifact, isTableArtifact } from "$lib/artifacts/types";

export type AssistantChatPart =
  | { id: string; kind: "text"; artifact: TextArtifact }
  | { id: string; kind: "chart"; artifact: ChartArtifact }
  | { id: string; kind: "table"; artifact: TableArtifact }
  | { id: string; kind: "debug"; payload: Record<string, unknown> };

export function assistantChatParts(
  artifacts: Artifact[],
  fallbackAnswer: string,
  debugPayload: Record<string, unknown> | null
): AssistantChatPart[] {
  const parts: AssistantChatPart[] = [];

  textArtifactsOrFallback(artifacts, fallbackAnswer).forEach((artifact, index) => {
    parts.push({ id: `text-${index}-${artifact.role}`, kind: "text", artifact });
  });

  artifacts.filter(isChartArtifact).forEach((artifact, index) => {
    parts.push({ id: `chart-${index}-${artifact.title}`, kind: "chart", artifact });
  });

  artifacts.filter(isTableArtifact).forEach((artifact, index) => {
    parts.push({ id: `table-${index}-${artifact.title}`, kind: "table", artifact });
  });

  if (debugPayload) {
    parts.push({ id: "debug-payload", kind: "debug", payload: debugPayload });
  }

  return parts;
}
