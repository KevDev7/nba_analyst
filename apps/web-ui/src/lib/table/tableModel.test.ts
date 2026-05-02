import { describe, expect, it } from "vitest";

import { formatCellValue } from "./format";
import { nextSortingState, renderArtifactTable } from "./tableModel";
import type { TableArtifact } from "$lib/artifacts/types";

const artifact: TableArtifact = {
  kind: "table",
  title: "Top players",
  columns: [
    { id: "player", label: "Player", type: "text" },
    { id: "points", label: "Points", type: "number" },
    { id: "game_date", label: "Game Date", type: "date" }
  ],
  rows: [
    { player: "Beta", points: 12.3456, game_date: "2026-01-02" },
    { player: "Alpha", points: 21, game_date: "2026-01-01" },
    { player: "Gamma", points: null, game_date: "2026-01-03" }
  ],
  row_count: 3,
  displayed_row_count: 3,
  display_limit: 50
};

describe("table artifact model", () => {
  it("sorts typed number columns through TanStack Table Core", () => {
    const rendered = renderArtifactTable(artifact, [{ id: "points", desc: true }]);

    expect(rendered.rows.map((row) => row.cells[0].value)).toEqual(["Alpha", "Beta", "Gamma"]);
    expect(rendered.headers[1].sortDirection).toBe("desc");
  });

  it("cycles sort state from ascending to descending to server order", () => {
    expect(nextSortingState([], "points")).toEqual([{ id: "points", desc: false }]);
    expect(nextSortingState([{ id: "points", desc: false }], "points")).toEqual([{ id: "points", desc: true }]);
    expect(nextSortingState([{ id: "points", desc: true }], "points")).toEqual([]);
  });

  it("formats nulls and numbers for display without mutating table values", () => {
    expect(formatCellValue(null, "number")).toBe("—");
    expect(formatCellValue(12.3456, "number")).toBe("12.346");
    expect(formatCellValue(12, "integer")).toBe("12");
  });
});
