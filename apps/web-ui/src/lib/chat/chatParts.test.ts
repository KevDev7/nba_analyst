import { describe, expect, it } from "vitest";

import type { Artifact } from "$lib/artifacts/types";
import { assistantChatParts } from "./chatParts";

const artifacts: Artifact[] = [
  { kind: "text", role: "interpretation", text: "Interpreted as: average points by month." },
  { kind: "text", role: "summary", text: "Monthly averages are shown below." },
  {
    kind: "text",
    role: "assumptions",
    text: "Ignored chart request.",
    items: ["Ignored chart request."]
  },
  {
    kind: "chart",
    renderer: "vega_lite",
    title: "Monthly averages",
    spec: { mark: "line" }
  },
  {
    kind: "table",
    title: "Monthly averages",
    columns: [{ id: "month", label: "Month", type: "date" }],
    rows: [{ month: "2026-01" }],
    row_count: 1,
    displayed_row_count: 1,
    display_limit: 50
  }
];

describe("assistantChatParts", () => {
  it("groups answer text and keeps chart/table/debug as separate assistant chat parts", () => {
    expect(assistantChatParts(artifacts, "", { debug: true }).map((part) => part.kind)).toEqual([
      "answer",
      "chart",
      "table",
      "debug"
    ]);
  });

  it("combines interpretation, summary, and assumptions into one answer part", () => {
    const [answer] = assistantChatParts(artifacts, "", null);

    expect(answer).toMatchObject({
      kind: "answer",
      artifact: {
        interpretation: { text: "Interpreted as: average points by month." },
        summary: { text: "Monthly averages are shown below." },
        assumptions: { items: ["Ignored chart request."] }
      }
    });
  });

  it("uses the fallback answer when no structured text artifact exists", () => {
    expect(assistantChatParts([], "Fallback answer", null)).toEqual([
      {
        id: "answer",
        kind: "answer",
        artifact: {
          kind: "answer",
          summary: { kind: "text", role: "answer", text: "Fallback answer" }
        }
      }
    ]);
  });
});
