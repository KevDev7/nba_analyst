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
AnalysisRuntimeName = Literal["local_trusted"]
ChartRenderer = Literal["vega_lite", "plotly"]


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


class ChartOperation(BaseModel):
    # Controlled chart operation. This is intentionally not arbitrary Python code.
    kind: Literal["line_chart", "bar_chart"]
    input_table_id: str
    x: str
    y: str
    series: Optional[str] = None
    title: Optional[str] = None
    renderer: ChartRenderer = "vega_lite"
    metadata: Dict[str, Any] = Field(default_factory=dict)


AnalysisOperation = Union[ChartOperation]


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
        table = tables_by_id.get(self.operation.input_table_id)
        if table is None:
            raise ValueError(f"Operation references unknown table: {self.operation.input_table_id}")
        column_ids = {column.id for column in table.columns}
        referenced_columns = [self.operation.x, self.operation.y]
        if self.operation.series:
            referenced_columns.append(self.operation.series)
        missing_columns = [column for column in referenced_columns if column not in column_ids]
        if missing_columns:
            raise ValueError(f"Operation references unknown columns: {', '.join(missing_columns)}")
        return self


class ChartArtifact(BaseModel):
    # Provider-neutral chart artifact. Vega-Lite is the first renderer, not the only one.
    kind: Literal["chart"] = "chart"
    renderer: ChartRenderer
    title: str
    spec: Dict[str, Any]
    data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


AnalysisArtifact = ChartArtifact


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
    artifacts: List[AnalysisArtifact] = Field(default_factory=list)
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
