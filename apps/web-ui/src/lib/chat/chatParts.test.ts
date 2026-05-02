import { describe, expect, it } from "vitest";

import type { Artifact } from "$lib/artifacts/types";
import { assistantChatParts } from "./chatParts";

const artifacts: Artifact[] = [
  { kind: "text", role: "interpretation", text: "Interpreted as: average points by month." },
  { kind: "text", role: "summary", text: "Monthly averages are shown below." },
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
  it("turns structured artifacts into separately renderable assistant chat parts", () => {
    expect(assistantChatParts(artifacts, "", { debug: true }).map((part) => part.kind)).toEqual([
      "text",
      "text",
      "chart",
      "table",
      "debug"
    ]);
  });

  it("uses the fallback answer when no structured text artifact exists", () => {
    expect(assistantChatParts([], "Fallback answer", null)).toEqual([
      {
        id: "text-0-answer",
        kind: "text",
        artifact: { kind: "text", role: "answer", text: "Fallback answer" }
      }
    ]);
  });
});
