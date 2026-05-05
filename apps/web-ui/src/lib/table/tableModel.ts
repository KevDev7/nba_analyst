import {
  createTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type ColumnDef,
  type PaginationState,
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
  pagination: {
    pageIndex: number;
    pageSize: number;
    pageCount: number;
    rowCount: number;
    needsPagination: boolean;
    canPreviousPage: boolean;
    canNextPage: boolean;
  };
};

export type { PaginationState, SortingState };

export const TABLE_PAGE_SIZE = 10;

export function createArtifactTable(
  artifact: TableArtifact,
  sorting: SortingState,
  pagination: PaginationState
): Table<TableRow> {
  const columnTypes = columnTypeMap(artifact);
  const rowCount = artifact.rows.length;
  const pageCount = tablePageCount(rowCount, pagination.pageSize);
  const pageIndex = clampPageIndex(pagination.pageIndex, pageCount);
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
    state: { sorting, pagination: { pageIndex, pageSize: pagination.pageSize }, columnPinning: { left: [], right: [] } },
    onStateChange: () => undefined,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    renderFallbackValue: null
  });
}

export function renderArtifactTable(
  artifact: TableArtifact,
  sorting: SortingState,
  pagination: PaginationState = { pageIndex: 0, pageSize: TABLE_PAGE_SIZE }
): RenderedTable {
  const table = createArtifactTable(artifact, sorting, pagination);
  const columnTypes = columnTypeMap(artifact);
  const headerGroup = table.getHeaderGroups()[0];
  const rowCount = artifact.rows.length;
  const pageSize = table.getState().pagination.pageSize;
  const pageCount = tablePageCount(rowCount, pageSize);
  const pageIndex = table.getState().pagination.pageIndex;

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
    })),
    pagination: {
      pageIndex,
      pageSize,
      pageCount,
      rowCount,
      needsPagination: rowCount > pageSize,
      canPreviousPage: table.getCanPreviousPage(),
      canNextPage: table.getCanNextPage()
    }
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

function tablePageCount(rowCount: number, pageSize: number): number {
  if (rowCount <= 0 || pageSize <= 0) {
    return 1;
  }
  return Math.ceil(rowCount / pageSize);
}

function clampPageIndex(pageIndex: number, pageCount: number): number {
  return Math.min(Math.max(pageIndex, 0), Math.max(pageCount - 1, 0));
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
