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

  it("paginates tables larger than the fixed page size", () => {
    const paginatedArtifact: TableArtifact = {
      ...artifact,
      rows: Array.from({ length: 12 }, (_, index) => ({
        player: `Player ${index + 1}`,
        points: index + 1,
        game_date: "2026-01-01"
      })),
      row_count: 12,
      displayed_row_count: 12
    };

    const firstPage = renderArtifactTable(paginatedArtifact, [], { pageIndex: 0, pageSize: 10 });
    const secondPage = renderArtifactTable(paginatedArtifact, [], { pageIndex: 1, pageSize: 10 });

    expect(firstPage.rows).toHaveLength(10);
    expect(secondPage.rows.map((row) => row.cells[0].value)).toEqual(["Player 11", "Player 12"]);
    expect(firstPage.pagination).toMatchObject({
      pageIndex: 0,
      pageSize: 10,
      pageCount: 2,
      rowCount: 12,
      needsPagination: true,
      canPreviousPage: false,
      canNextPage: true
    });
    expect(secondPage.pagination.canPreviousPage).toBe(true);
    expect(secondPage.pagination.canNextPage).toBe(false);
  });

  it("sorts before paginating", () => {
    const paginatedArtifact: TableArtifact = {
      ...artifact,
      rows: Array.from({ length: 12 }, (_, index) => ({
        player: `Player ${index + 1}`,
        points: index + 1,
        game_date: "2026-01-01"
      })),
      row_count: 12,
      displayed_row_count: 12
    };

    const rendered = renderArtifactTable(paginatedArtifact, [{ id: "points", desc: true }], {
      pageIndex: 0,
      pageSize: 10
    });

    expect(rendered.rows.map((row) => row.cells[0].value)).toEqual([
      "Player 12",
      "Player 11",
      "Player 10",
      "Player 9",
      "Player 8",
      "Player 7",
      "Player 6",
      "Player 5",
      "Player 4",
      "Player 3"
    ]);
  });

  it("does not mark small tables as needing pagination", () => {
    const rendered = renderArtifactTable(artifact, []);

    expect(rendered.rows).toHaveLength(3);
    expect(rendered.pagination).toMatchObject({
      pageIndex: 0,
      pageSize: 10,
      pageCount: 1,
      rowCount: 3,
      needsPagination: false,
      canPreviousPage: false,
      canNextPage: false
    });
  });

  it("formats nulls and numbers for display without mutating table values", () => {
    expect(formatCellValue(null, "number")).toBe("—");
    expect(formatCellValue(12.3456, "number")).toBe("12.346");
    expect(formatCellValue(12, "integer")).toBe("12");
  });
});
