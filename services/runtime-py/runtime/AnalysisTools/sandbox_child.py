from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import re
import sys
import traceback
from typing import Any


FORBIDDEN_IMPORTS = {
    "builtins",
    "duckdb",
    "http",
    "importlib",
    "os",
    "pathlib",
    "requests",
    "shutil",
    "socket",
    "sqlalchemy",
    "sqlite3",
    "subprocess",
    "sys",
    "urllib",
}
FORBIDDEN_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
FORBIDDEN_NAMES = {
    "__builtins__",
    "builtins",
    "duckdb",
    "environ",
    "importlib",
    "os",
    "pathlib",
    "requests",
    "shutil",
    "socket",
    "sqlite3",
    "sql",
    "sqlalchemy",
    "subprocess",
    "sys",
    "urllib",
}
SQL_AUTHORING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bselect\b[\s\S]{0,120}\bfrom\b",
        r"\bwith\b[\s\S]{0,120}\bas\b",
        r"\b(insert|update|delete|drop|alter|create|copy|attach|pragma|load|install)\b",
    ]
]


class SandboxValidationError(Exception):
    pass


class CodeValidator(ast.NodeVisitor):
    def __init__(self, allowed_imports: set[str]) -> None:
        self.allowed_imports = allowed_imports

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._validate_import(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            raise SandboxValidationError("Relative imports are not allowed.")
        self._validate_import(node.module)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            raise SandboxValidationError(f"Call to '{node.func.id}' is not allowed.")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES or "__" in node.id:
            raise SandboxValidationError(f"Name '{node.id}' is not allowed.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__") or node.attr in {"environ", "execute", "executemany", "cursor", "connect", "system", "popen", "read_sql"}:
            raise SandboxValidationError(f"Attribute '{node.attr}' is not allowed.")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _looks_like_sql_authoring(node.value):
            raise SandboxValidationError("SQL authoring is not allowed in sandbox code.")
        self.generic_visit(node)

    def _validate_import(self, module_name: str) -> None:
        root = module_name.split(".", 1)[0]
        if root in FORBIDDEN_IMPORTS or root not in self.allowed_imports:
            raise SandboxValidationError(f"Import '{module_name}' is not allowed.")


def main() -> None:
    payload = json.loads(sys.stdin.read())
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        result = _run_payload(payload, stdout, stderr)
    except Exception as exc:
        result = {
            "ok": False,
            "error": {
                "code": "python_code_failed",
                "message": str(exc),
            },
        }
        traceback.print_exc(file=stderr)
    result["stdout"] = stdout.getvalue()
    result["stderr"] = stderr.getvalue()
    sys.stdout.write(json.dumps(result, sort_keys=True))


def _run_payload(payload: dict[str, Any], stdout: io.StringIO, stderr: io.StringIO) -> dict[str, Any]:
    code = payload["code"]
    allowed_imports = set(payload.get("import_allowlist", []))
    tree = ast.parse(code, mode="exec")
    CodeValidator(allowed_imports).visit(tree)

    tables = copy.deepcopy(payload["tables"])
    namespace: dict[str, Any] = {
        "__builtins__": _safe_builtins(allowed_imports),
        "tables": tables,
        "outputs": {"tables": [], "metrics": [], "findings": []},
    }
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exec(compile(tree, "<sandboxed-python-analysis>", "exec"), namespace, namespace)
    outputs = namespace.get("outputs")
    if not isinstance(outputs, dict):
        raise SandboxValidationError("Sandbox code must leave outputs as an object.")
    return {"ok": True, "outputs": outputs}


def _safe_builtins(allowed_imports: set[str]) -> dict[str, Any]:
    safe: dict[str, Any] = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "pow": pow,
        "print": print,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }

    def safe_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
        root = name.split(".", 1)[0]
        if level != 0 or root not in allowed_imports:
            raise ImportError(f"Import '{name}' is not allowed.")
        return __import__(name, globals, locals, fromlist, level)

    safe["__import__"] = safe_import
    return safe


def _looks_like_sql_authoring(value: str) -> bool:
    return any(pattern.search(value) for pattern in SQL_AUTHORING_PATTERNS)


if __name__ == "__main__":
    main()
