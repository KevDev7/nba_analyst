import type { ArtifactColumnType } from "$lib/artifacts/types";

export function formatCellValue(value: unknown, columnType: ArtifactColumnType): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if ((columnType === "number" || columnType === "integer") && typeof value === "number") {
    return new Intl.NumberFormat("en-US", {
      maximumFractionDigits: columnType === "integer" ? 0 : 3
    }).format(value);
  }
  return String(value);
}

export function columnAlignment(columnType: ArtifactColumnType): "left" | "right" {
  return columnType === "number" || columnType === "integer" ? "right" : "left";
}
