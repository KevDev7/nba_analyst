import { describe, expect, it } from "vitest";

import { textArtifactsOrFallback } from "./text";
import { isChartArtifact } from "./types";
import type { Artifact, ChartArtifact } from "./types";

describe("textArtifactsOrFallback", () => {
  it("prefers structured text artifacts over the fallback answer", () => {
    const artifacts: Artifact[] = [
      { kind: "text", role: "summary", text: "Structured summary" },
      { kind: "table", title: "Rows", columns: [], rows: [], row_count: 0, displayed_row_count: 0, display_limit: 50 }
    ];

    expect(textArtifactsOrFallback(artifacts, "Fallback answer")).toEqual([
      { kind: "text", role: "summary", text: "Structured summary" }
    ]);
  });

  it("uses the answer string when older responses do not include text artifacts", () => {
    expect(textArtifactsOrFallback([], "Fallback answer")).toEqual([
      { kind: "text", role: "answer", text: "Fallback answer" }
    ]);
  });
});

describe("isChartArtifact", () => {
  it("recognizes structured chart artifacts", () => {
    const artifact: ChartArtifact = {
      kind: "chart",
      renderer: "vega_lite",
      title: "Monthly average points",
      spec: { mark: "line" }
    };

    expect(isChartArtifact(artifact)).toBe(true);
  });

  it("rejects chart-shaped artifacts without specs", () => {
    expect(isChartArtifact({ kind: "chart", renderer: "vega_lite", title: "Missing spec" })).toBe(false);
  });
});
