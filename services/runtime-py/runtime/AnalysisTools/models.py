# Purpose:
# Define provider-neutral contracts for Python analysis tools.
#
# Uses:
# - structured rows produced by the grounded runtime
# - controlled operation specs owned by the product
#
# Produces:
# - typed analysis requests, results, logs, errors, and artifacts
#
# Next:
# - assistant/runtime wiring that calls the analysis tool boundary

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


ColumnType = Literal["text", "number", "integer", "date", "boolean"]
AnalysisRuntimeName = Literal["local_trusted", "local_sandbox"]
ChartRenderer = Literal["vega_lite", "plotly"]
ChartOrientation = Literal["vertical", "horizontal"]
ChartSortChannel = Literal["x", "y"]
ChartSortOrder = Literal["ascending", "descending"]
DerivedSortDirection = Literal["asc", "desc"]
JoinType = Literal["inner", "left", "outer"]


class AnalysisTableColumn(BaseModel):
    # One column available to a Python analysis operation.
    id: str
    label: str
    type: ColumnType = "text"


class AnalysisTable(BaseModel):
    # Structured table input handed to the analysis tool.
    id: str
    title: str = ""
    columns: List[AnalysisTableColumn]
    rows: List[Dict[str, Any]]
    row_count: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_rows_use_declared_columns(self) -> "AnalysisTable":
        column_ids = {column.id for column in self.columns}
        unknown_columns = sorted(
            {
                key
                for row in self.rows
                for key in row
                if key not in column_ids
            }
        )
        if unknown_columns:
            raise ValueError(f"Rows contain undeclared columns: {', '.join(unknown_columns)}")
        return self


class ChartSort(BaseModel):
    channel: ChartSortChannel
    field: Optional[str] = None
    order: Optional[ChartSortOrder] = None


class ChartOperation(BaseModel):
    # Controlled chart operation. This is intentionally not arbitrary Python code.
    kind: Literal["line_chart", "bar_chart", "point_chart"]
    input_table_id: str
    x: str
    y: str
    series: Optional[str] = None
    orientation: ChartOrientation = "vertical"
    sort: Optional[ChartSort] = None
    title: Optional[str] = None
    renderer: ChartRenderer = "vega_lite"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DerivedSort(BaseModel):
    by: str
    direction: DerivedSortDirection = "desc"


class JoinAndDeltaOperation(BaseModel):
    # Controlled derived-analysis operation. Computes right_metric - left_metric
    # after joining approved input tables.
    kind: Literal["join_and_delta"]
    left_table_id: str
    right_table_id: str
    join_keys: List[str]
    left_metric: str
    right_metric: str
    output_metric: str
    left_output_column: Optional[str] = None
    right_output_column: Optional[str] = None
    join_type: JoinType = "inner"
    sort: Optional[DerivedSort] = None
    limit: Optional[int] = Field(default=None, ge=1, le=5000)
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_join_keys(self) -> "JoinAndDeltaOperation":
        if not self.join_keys:
            raise ValueError("join_and_delta requires at least one join key.")
        return self


class RankExtremesOperation(BaseModel):
    # Controlled derived-analysis operation. Sorts one approved table by a
    # numeric metric and adds a deterministic rank column.
    kind: Literal["rank_extremes"]
    input_table_id: str
    metric: str
    direction: DerivedSortDirection = "desc"
    limit: int = Field(default=10, ge=1, le=5000)
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CorrelationOperation(BaseModel):
    # Controlled derived-analysis operation. Joins two approved metric tables
    # and computes a Pearson correlation over matched rows.
    kind: Literal["correlation"]
    left_table_id: str
    right_table_id: str
    join_keys: List[str]
    left_metric: str
    right_metric: str
    left_output_column: Optional[str] = None
    right_output_column: Optional[str] = None
    method: Literal["pearson"] = "pearson"
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_join_keys(self) -> "CorrelationOperation":
        if not self.join_keys:
            raise ValueError("correlation requires at least one join key.")
        return self


class PercentChangeOperation(BaseModel):
    # Controlled derived-analysis operation. Computes
    # ((right_metric - left_metric) / abs(left_metric)) * 100 after joining
    # approved input tables.
    kind: Literal["percent_change"]
    left_table_id: str
    right_table_id: str
    join_keys: List[str]
    left_metric: str
    right_metric: str
    output_metric: str = "percent_change"
    left_output_column: Optional[str] = None
    right_output_column: Optional[str] = None
    join_type: JoinType = "inner"
    sort: Optional[DerivedSort] = None
    limit: Optional[int] = Field(default=None, ge=1, le=5000)
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_join_keys(self) -> "PercentChangeOperation":
        if not self.join_keys:
            raise ValueError("percent_change requires at least one join key.")
        return self


class ZScoreOutliersOperation(BaseModel):
    # Controlled derived-analysis operation. Adds a z-score column and returns
    # rows whose absolute z-score meets the threshold.
    kind: Literal["zscore_outliers"]
    input_table_id: str
    metric: str
    threshold: float = Field(default=2.0, ge=0)
    direction: Literal["both", "high", "low"] = "both"
    limit: Optional[int] = Field(default=None, ge=1, le=5000)
    title: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PythonCodeSandboxPolicy(BaseModel):
    max_input_rows: int = Field(default=5000, ge=1, le=50000)
    max_output_rows: int = Field(default=500, ge=1, le=5000)
    timeout_ms: int = Field(default=5000, ge=100, le=30000)
    memory_mb: Optional[int] = Field(default=256, ge=64, le=2048)
    import_allowlist: List[str] = Field(default_factory=lambda: ["math", "statistics", "json"])
    no_network: Literal[True] = True
    no_filesystem_except_scratch: Literal[True] = True
    no_environment_access: Literal[True] = True

    @model_validator(mode="after")
    def validate_import_allowlist(self) -> "PythonCodeSandboxPolicy":
        allowed = {"math", "statistics", "json"}
        unknown = sorted(set(self.import_allowlist) - allowed)
        if unknown:
            raise ValueError(f"Unsupported sandbox imports: {', '.join(unknown)}")
        return self


class PythonCodeOutputTableSchema(BaseModel):
    id: str
    title: str = ""
    columns: List[AnalysisTableColumn]

    @model_validator(mode="after")
    def validate_columns(self) -> "PythonCodeOutputTableSchema":
        if not self.columns:
            raise ValueError("python_code output table schemas require at least one column.")
        column_ids = [column.id for column in self.columns]
        if len(set(column_ids)) != len(column_ids):
            raise ValueError("python_code output table schemas cannot contain duplicate columns.")
        return self


class PythonCodeOperation(BaseModel):
    # Gated arbitrary-code operation. Code may analyze only declared input
    # tables and must return structured outputs matching declared schemas.
    kind: Literal["python_code"]
    code: str = Field(min_length=1, max_length=20000)
    input_table_ids: List[str]
    output_tables: List[PythonCodeOutputTableSchema]
    policy: PythonCodeSandboxPolicy = Field(default_factory=PythonCodeSandboxPolicy)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "PythonCodeOperation":
        if not self.input_table_ids:
            raise ValueError("python_code requires at least one input table.")
        if not self.output_tables:
            raise ValueError("python_code requires at least one declared output table.")
        if len(set(self.input_table_ids)) != len(self.input_table_ids):
            raise ValueError("python_code input table ids must be unique.")
        output_ids = [table.id for table in self.output_tables]
        if len(set(output_ids)) != len(output_ids):
            raise ValueError("python_code output table ids must be unique.")
        return self


AnalysisOperation = Union[
    ChartOperation,
    JoinAndDeltaOperation,
    RankExtremesOperation,
    CorrelationOperation,
    PercentChangeOperation,
    ZScoreOutliersOperation,
    PythonCodeOperation,
]


class AnalysisRequest(BaseModel):
    # One analysis-tool call. Future agent tools can call this boundary directly.
    tool: Literal["python_analysis"] = "python_analysis"
    runtime: AnalysisRuntimeName = "local_trusted"
    tables: List[AnalysisTable]
    operation: AnalysisOperation = Field(discriminator="kind")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_operation_references_existing_table_and_columns(self) -> "AnalysisRequest":
        tables_by_id = {table.id: table for table in self.tables}
        if isinstance(self.operation, ChartOperation):
            self._validate_chart_operation(tables_by_id)
        elif isinstance(self.operation, JoinAndDeltaOperation):
            self._validate_join_and_delta_operation(tables_by_id)
        elif isinstance(self.operation, RankExtremesOperation):
            self._validate_rank_extremes_operation(tables_by_id)
        elif isinstance(self.operation, CorrelationOperation):
            self._validate_correlation_operation(tables_by_id)
        elif isinstance(self.operation, PercentChangeOperation):
            self._validate_percent_change_operation(tables_by_id)
        elif isinstance(self.operation, ZScoreOutliersOperation):
            self._validate_zscore_outliers_operation(tables_by_id)
        elif isinstance(self.operation, PythonCodeOperation):
            self._validate_python_code_operation(tables_by_id)
        return self

    def _validate_chart_operation(self, tables_by_id: Dict[str, AnalysisTable]) -> None:
        table = tables_by_id.get(self.operation.input_table_id)
        if table is None:
            raise ValueError(f"Operation references unknown table: {self.operation.input_table_id}")
        column_ids = {column.id for column in table.columns}
        referenced_columns = [self.operation.x, self.operation.y]
        if self.operation.series:
            referenced_columns.append(self.operation.series)
        if self.operation.sort and self.operation.sort.field:
            referenced_columns.append(self.operation.sort.field)
        missing_columns = [column for column in referenced_columns if column not in column_ids]
        if missing_columns:
            raise ValueError(f"Operation references unknown columns: {', '.join(missing_columns)}")

    def _validate_join_and_delta_operation(self, tables_by_id: Dict[str, AnalysisTable]) -> None:
        left = tables_by_id.get(self.operation.left_table_id)
        right = tables_by_id.get(self.operation.right_table_id)
        if left is None:
            raise ValueError(f"Operation references unknown table: {self.operation.left_table_id}")
        if right is None:
            raise ValueError(f"Operation references unknown table: {self.operation.right_table_id}")
        left_columns = {column.id for column in left.columns}
        right_columns = {column.id for column in right.columns}
        left_required = [*self.operation.join_keys, self.operation.left_metric]
        right_required = [*self.operation.join_keys, self.operation.right_metric]
        missing_left = [column for column in left_required if column not in left_columns]
        missing_right = [column for column in right_required if column not in right_columns]
        if missing_left:
            raise ValueError(f"Operation references unknown left columns: {', '.join(missing_left)}")
        if missing_right:
            raise ValueError(f"Operation references unknown right columns: {', '.join(missing_right)}")
        if self.operation.sort and self.operation.sort.by not in {
            *self.operation.join_keys,
            self.operation.left_output_column or f"left_{self.operation.left_metric}",
            self.operation.right_output_column or f"right_{self.operation.right_metric}",
            self.operation.output_metric,
        }:
            raise ValueError(f"Operation references unknown sort column: {self.operation.sort.by}")

    def _validate_rank_extremes_operation(self, tables_by_id: Dict[str, AnalysisTable]) -> None:
        table = tables_by_id.get(self.operation.input_table_id)
        if table is None:
            raise ValueError(f"Operation references unknown table: {self.operation.input_table_id}")
        column_ids = {column.id for column in table.columns}
        if self.operation.metric not in column_ids:
            raise ValueError(f"Operation references unknown columns: {self.operation.metric}")

    def _validate_correlation_operation(self, tables_by_id: Dict[str, AnalysisTable]) -> None:
        left = tables_by_id.get(self.operation.left_table_id)
        right = tables_by_id.get(self.operation.right_table_id)
        if left is None:
            raise ValueError(f"Operation references unknown table: {self.operation.left_table_id}")
        if right is None:
            raise ValueError(f"Operation references unknown table: {self.operation.right_table_id}")
        left_columns = {column.id for column in left.columns}
        right_columns = {column.id for column in right.columns}
        missing_left = [
            column
            for column in [*self.operation.join_keys, self.operation.left_metric]
            if column not in left_columns
        ]
        missing_right = [
            column
            for column in [*self.operation.join_keys, self.operation.right_metric]
            if column not in right_columns
        ]
        if missing_left:
            raise ValueError(f"Operation references unknown left columns: {', '.join(missing_left)}")
        if missing_right:
            raise ValueError(f"Operation references unknown right columns: {', '.join(missing_right)}")

    def _validate_percent_change_operation(self, tables_by_id: Dict[str, AnalysisTable]) -> None:
        left = tables_by_id.get(self.operation.left_table_id)
        right = tables_by_id.get(self.operation.right_table_id)
        if left is None:
            raise ValueError(f"Operation references unknown table: {self.operation.left_table_id}")
        if right is None:
            raise ValueError(f"Operation references unknown table: {self.operation.right_table_id}")
        left_columns = {column.id for column in left.columns}
        right_columns = {column.id for column in right.columns}
        missing_left = [
            column
            for column in [*self.operation.join_keys, self.operation.left_metric]
            if column not in left_columns
        ]
        missing_right = [
            column
            for column in [*self.operation.join_keys, self.operation.right_metric]
            if column not in right_columns
        ]
        if missing_left:
            raise ValueError(f"Operation references unknown left columns: {', '.join(missing_left)}")
        if missing_right:
            raise ValueError(f"Operation references unknown right columns: {', '.join(missing_right)}")

    def _validate_zscore_outliers_operation(self, tables_by_id: Dict[str, AnalysisTable]) -> None:
        table = tables_by_id.get(self.operation.input_table_id)
        if table is None:
            raise ValueError(f"Operation references unknown table: {self.operation.input_table_id}")
        column_ids = {column.id for column in table.columns}
        if self.operation.metric not in column_ids:
            raise ValueError(f"Operation references unknown columns: {self.operation.metric}")

    def _validate_python_code_operation(self, tables_by_id: Dict[str, AnalysisTable]) -> None:
        if self.runtime != "local_sandbox":
            raise ValueError("python_code operations require runtime='local_sandbox'.")
        missing_tables = [table_id for table_id in self.operation.input_table_ids if table_id not in tables_by_id]
        if missing_tables:
            raise ValueError(f"Operation references unknown table: {', '.join(missing_tables)}")
        oversized = [
            table.id
            for table in self.tables
            if table.id in self.operation.input_table_ids
            and len(table.rows) > self.operation.policy.max_input_rows
        ]
        if oversized:
            raise ValueError(f"python_code input tables exceed max_input_rows: {', '.join(oversized)}")


class ChartArtifact(BaseModel):
    # Provider-neutral chart artifact. Vega-Lite is the first renderer, not the only one.
    kind: Literal["chart"] = "chart"
    renderer: ChartRenderer
    title: str
    spec: Dict[str, Any]
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


AnalysisArtifact = ChartArtifact


class AnalysisFinding(BaseModel):
    kind: str
    text: str
    evidence_table_id: Optional[str] = None
    row_refs: List[int] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalysisLog(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalysisToolError(BaseModel):
    code: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    ok: bool
    tables: List[AnalysisTable] = Field(default_factory=list)
    artifacts: List[AnalysisArtifact] = Field(default_factory=list)
    findings: List[AnalysisFinding] = Field(default_factory=list)
    logs: List[AnalysisLog] = Field(default_factory=list)
    error: Optional[AnalysisToolError] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_success_error_shape(self) -> "AnalysisResult":
        if self.ok and self.error is not None:
            raise ValueError("Successful analysis result cannot include an error.")
        if not self.ok and self.error is None:
            raise ValueError("Failed analysis result must include an error.")
        return self
