from __future__ import annotations

from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel, Field

from apps.assistant.trace import new_id
from apps.assistant.workspace import RunWorkspace


GOVERNED_TOOL_NAMES = {
    "ontology_catalog.inspect",
    "semantic_query.plan_execute",
    "python_analysis.run",
    "chart_generation.run",
    "artifact_renderer.render",
    "answer_composer.compose",
}

MODEL_VISIBLE_TOOL_NAMES = {
    "ontology_catalog.inspect",
    "semantic_query.plan_execute",
    "python_analysis.run",
    "chart_generation.run",
    "artifact_renderer.render",
}

FORBIDDEN_TOOL_NAMES = {
    "raw_sql",
    "raw_python",
    "arbitrary_python",
    "python_code",
    "duckdb.execute",
    "sql.execute",
    "governed_sql.execute",
}


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    model_visible: bool = True


class ToolContext(BaseModel):
    question: str
    debug: bool = False
    workspace: RunWorkspace = Field(default_factory=RunWorkspace)


class ToolResult(BaseModel):
    ok: bool
    tool_name: str
    tool_call_id: str = Field(default_factory=lambda: new_id("tc"))
    output: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    error: Optional[dict[str, Any]] = None


class ToolExecutor(Protocol):
    def __call__(self, payload: dict[str, Any], context: ToolContext) -> ToolResult:
        ...


ForbiddenPayloadChecker = Callable[[dict[str, Any]], bool]


class ToolRegistry:
    def __init__(
        self,
        *,
        allowed_tools: set[str] | None = None,
        forbidden_tools: set[str] | None = None,
        forbidden_payload_checker: ForbiddenPayloadChecker | None = None,
    ) -> None:
        self.allowed_tools = set(allowed_tools or GOVERNED_TOOL_NAMES)
        self.forbidden_tools = set(forbidden_tools or FORBIDDEN_TOOL_NAMES)
        self._forbidden_payload_checker = forbidden_payload_checker
        self._specs: dict[str, ToolSpec] = {}
        self._executors: dict[str, ToolExecutor] = {}

    def register(self, spec: ToolSpec, executor: ToolExecutor) -> None:
        if spec.name in self.forbidden_tools or spec.name not in self.allowed_tools:
            raise ValueError(f"Tool '{spec.name}' is not allowed.")
        self._specs[spec.name] = spec
        self._executors[spec.name] = executor

    def execute(self, name: str, payload: dict[str, Any], context: ToolContext) -> ToolResult:
        if name in self.forbidden_tools or name not in self._executors:
            return ToolResult(
                ok=False,
                tool_name=name,
                error={"code": "forbidden_tool", "message": f"Tool '{name}' is not allowed."},
            )
        if self._forbidden_payload_checker is not None and self._forbidden_payload_checker(payload):
            return ToolResult(
                ok=False,
                tool_name=name,
                error={"code": "forbidden_tool_payload", "message": "Tool payload references a forbidden raw capability."},
            )
        try:
            return self._executors[name](payload, context)
        except Exception as exc:
            return ToolResult(
                ok=False,
                tool_name=name,
                error={"code": "tool_execution_failed", "message": str(exc)},
            )

    @property
    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())
