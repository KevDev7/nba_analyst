import { textArtifactsOrFallback } from "$lib/artifacts/text";
import type { Artifact, ChartArtifact, TableArtifact, TextArtifact } from "$lib/artifacts/types";
import { isChartArtifact, isTableArtifact } from "$lib/artifacts/types";

export type AssistantChatPart =
  | { id: string; kind: "answer"; artifact: AnswerArtifact }
  | { id: string; kind: "chart"; artifact: ChartArtifact }
  | { id: string; kind: "table"; artifact: TableArtifact }
  | { id: string; kind: "debug"; payload: Record<string, unknown> };

export type AnswerArtifact = {
  kind: "answer";
  interpretation?: TextArtifact;
  summary?: TextArtifact;
  assumptions?: TextArtifact;
};

export function assistantChatParts(
  artifacts: Artifact[],
  fallbackAnswer: string,
  debugPayload: Record<string, unknown> | null
): AssistantChatPart[] {
  const parts: AssistantChatPart[] = [];
  const answer = answerArtifact(textArtifactsOrFallback(artifacts, fallbackAnswer));

  if (answer) {
    parts.push({ id: "answer", kind: "answer", artifact: answer });
  }

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

function answerArtifact(textArtifacts: TextArtifact[]): AnswerArtifact | null {
  if (textArtifacts.length === 0) {
    return null;
  }
  const interpretation = textArtifacts.find((artifact) => artifact.role === "interpretation");
  const summary =
    textArtifacts.find((artifact) => artifact.role === "summary") ??
    textArtifacts.find((artifact) => artifact.role === "answer") ??
    textArtifacts.find((artifact) => artifact.role !== "interpretation" && artifact.role !== "assumptions");
  const assumptions = textArtifacts.find((artifact) => artifact.role === "assumptions");

  return {
    kind: "answer",
    interpretation,
    summary,
    assumptions
  };
}
