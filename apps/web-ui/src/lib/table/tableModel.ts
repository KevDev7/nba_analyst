import {
  createTable,
  getCoreRowModel,
  getSortedRowModel,
  type ColumnDef,
  type Row,
  type SortingState,
  type Table
} from "@tanstack/table-core";

import type { ArtifactColumnType, TableArtifact } from "$lib/artifacts/types";

export type TableRow = Record<string, unknown>;

export type RenderedCell = {
  id: string;
  columnId: string;
  value: unknown;
};

export type RenderedRow = {
  id: string;
  cells: RenderedCell[];
};

export type RenderedHeader = {
  id: string;
  columnId: string;
  label: string;
  type: ArtifactColumnType;
  canSort: boolean;
  sortDirection: false | "asc" | "desc";
};

export type RenderedTable = {
  headers: RenderedHeader[];
  rows: RenderedRow[];
};

export type { SortingState };

export function createArtifactTable(artifact: TableArtifact, sorting: SortingState): Table<TableRow> {
  const columnTypes = columnTypeMap(artifact);
  const columns: Array<ColumnDef<TableRow>> = artifact.columns.map((column) => ({
    id: column.id,
    accessorFn: (row) => {
      const value = row[column.id];
      return value === null || value === "" ? undefined : value;
    },
    header: column.label,
    sortUndefined: "last",
    sortingFn: (rowA, rowB, columnId) => compareValues(rowA, rowB, columnId, columnTypes[columnId] ?? "text")
  }));

  return createTable<TableRow>({
    data: artifact.rows,
    columns,
    state: { sorting, columnPinning: { left: [], right: [] } },
    onStateChange: () => undefined,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    renderFallbackValue: null
  });
}

export function renderArtifactTable(artifact: TableArtifact, sorting: SortingState): RenderedTable {
  const table = createArtifactTable(artifact, sorting);
  const columnTypes = columnTypeMap(artifact);
  const headerGroup = table.getHeaderGroups()[0];

  return {
    headers: headerGroup.headers.map((header) => ({
      id: header.id,
      columnId: header.column.id,
      label: String(header.column.columnDef.header ?? header.column.id),
      type: columnTypes[header.column.id] ?? "text",
      canSort: header.column.getCanSort(),
      sortDirection: header.column.getIsSorted()
    })),
    rows: table.getRowModel().rows.map((row) => ({
      id: row.id,
      cells: row.getVisibleCells().map((cell) => ({
        id: cell.id,
        columnId: cell.column.id,
        value: cell.getValue()
      }))
    }))
  };
}

export function nextSortingState(sorting: SortingState, columnId: string): SortingState {
  const current = sorting[0];
  if (!current || current.id !== columnId) {
    return [{ id: columnId, desc: false }];
  }
  if (!current.desc) {
    return [{ id: columnId, desc: true }];
  }
  return [];
}

function columnTypeMap(artifact: TableArtifact): Record<string, ArtifactColumnType> {
  return Object.fromEntries(artifact.columns.map((column) => [column.id, column.type]));
}

function compareValues(
  rowA: Row<TableRow>,
  rowB: Row<TableRow>,
  columnId: string,
  columnType: ArtifactColumnType
): number {
  const left = rowA.getValue(columnId);
  const right = rowB.getValue(columnId);
  if (left === right) {
    return 0;
  }
  if (left === null || left === undefined || left === "") {
    return 1;
  }
  if (right === null || right === undefined || right === "") {
    return -1;
  }
  if (columnType === "number" || columnType === "integer") {
    return Number(left) - Number(right);
  }
  if (columnType === "date") {
    return Date.parse(String(left)) - Date.parse(String(right));
  }
  return String(left).localeCompare(String(right), undefined, {
    numeric: true,
    sensitivity: "base"
  });
}
