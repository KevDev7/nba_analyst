import type { Artifact, TextArtifact } from "./types";
import { isTextArtifact } from "./types";

export function textArtifactsOrFallback(artifacts: Artifact[], fallbackAnswer: string): TextArtifact[] {
  const textArtifacts = artifacts.filter(isTextArtifact);
  if (textArtifacts.length > 0) {
    return textArtifacts;
  }
  if (!fallbackAnswer.trim()) {
    return [];
  }
  return [
    {
      kind: "text",
      role: "answer",
      text: fallbackAnswer
    }
  ];
}
