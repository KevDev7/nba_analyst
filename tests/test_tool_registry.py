from __future__ import annotations

import json
import unittest

from apps.assistant.model_orchestration.tool_loop import build_default_registry
from apps.assistant.tools.registry import FORBIDDEN_TOOL_NAMES, GOVERNED_TOOL_NAMES, ToolContext, ToolRegistry, ToolResult, ToolSpec


class ToolRegistryTests(unittest.TestCase):
    def test_default_registry_registers_six_governed_tools(self) -> None:
        registry = build_default_registry()
        names = {spec.name for spec in registry.specs}

        self.assertEqual(names, GOVERNED_TOOL_NAMES)

    def test_registry_rejects_forbidden_tools(self) -> None:
        registry = ToolRegistry()

        with self.assertRaisesRegex(ValueError, "not allowed"):
            registry.register(ToolSpec(name=next(iter(FORBIDDEN_TOOL_NAMES)), description="bad"), lambda _p, _c: ToolResult(ok=True, tool_name="bad"))

    def test_registry_execute_rejects_unregistered_tool(self) -> None:
        registry = ToolRegistry()
        result = registry.execute("raw_sql", {"sql": "SELECT 1"}, ToolContext(question="q"))

        self.assertFalse(result.ok)
        self.assertEqual(result.error["code"], "forbidden_tool")

    def test_tool_specs_are_json_serializable(self) -> None:
        registry = build_default_registry()

        json.dumps([spec.model_dump() for spec in registry.specs], sort_keys=True)


if __name__ == "__main__":
    unittest.main()
