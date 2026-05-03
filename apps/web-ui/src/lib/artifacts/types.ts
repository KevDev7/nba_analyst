export type ArtifactKind = "text" | "table" | "debug" | string;

export type ArtifactColumnType = "text" | "number" | "integer" | "date" | string;

export type ChartRenderer = "vega_lite" | "plotly" | string;

export type ChartArtifactMetadata = {
  source_table_id?: string;
  operation_kind?: string;
  chart_family?: string;
  x?: string;
  y?: string;
  x_type?: ArtifactColumnType;
  y_type?: ArtifactColumnType;
  series?: string | null;
  orientation?: "vertical" | "horizontal" | string;
  series_count?: number;
  category_count?: number;
  row_count?: number;
  [key: string]: unknown;
};

export type TextArtifact = {
  kind: "text";
  role: string;
  text: string;
  items?: string[];
};

export type TableArtifact = {
  kind: "table";
  title: string;
  columns: Array<{
    id: string;
    label: string;
    type: ArtifactColumnType;
  }>;
  rows: Array<Record<string, unknown>>;
  row_count: number;
  displayed_row_count: number;
  display_limit: number;
};

export type ChartArtifact = {
  kind: "chart";
  renderer: ChartRenderer;
  title: string;
  spec: Record<string, unknown>;
  data?: Record<string, unknown>;
  metadata?: ChartArtifactMetadata;
};

export type DebugArtifact = {
  kind: "debug";
  title?: string;
  payload: unknown;
};

export type Artifact = TextArtifact | TableArtifact | ChartArtifact | DebugArtifact | Record<string, unknown>;

export type ChatRequest = {
  question: string;
  debug: boolean;
};

export type ChatResponse = {
  ok: boolean;
  answer?: string | null;
  error?: string | null;
  artifacts?: Artifact[];
  debug?: Record<string, unknown> | null;
};

export function isTextArtifact(artifact: Artifact): artifact is TextArtifact {
  return artifact.kind === "text" && typeof artifact.text === "string";
}

export function isTableArtifact(artifact: Artifact): artifact is TableArtifact {
  return artifact.kind === "table" && Array.isArray(artifact.columns) && Array.isArray(artifact.rows);
}

export function isChartArtifact(artifact: Artifact): artifact is ChartArtifact {
  return (
    artifact.kind === "chart" &&
    typeof artifact.renderer === "string" &&
    typeof artifact.title === "string" &&
    artifact.spec !== null &&
    typeof artifact.spec === "object" &&
    !Array.isArray(artifact.spec)
  );
}
