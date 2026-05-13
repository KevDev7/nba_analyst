from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .models import PythonCodeOperation


SANDBOX_ENABLED_ENV = "NBA_ENABLE_PYTHON_CODE_SANDBOX"
SANDBOX_BACKEND_ENV = "NBA_PYTHON_CODE_SANDBOX_BACKEND"
E2B_LIVE_TEST_ENV = "NBA_RUN_LIVE_E2B_TESTS"
LOCAL_BACKEND_ID = "local_beta"
LOCAL_RUNTIME_ID = "local_python_code_sandbox:v1"
LOCAL_SANDBOX_BACKEND = "macos_sandbox_exec"
LOCAL_SANDBOX_STATUS = "local_beta_only"
E2B_BACKEND_ID = "e2b_cloud"
E2B_RUNTIME_ID = "e2b_cloud_python_code_sandbox:v1"
E2B_SANDBOX_STATUS = "cloud_beta_gated"
MOCK_E2B_BACKEND_ID = "mock_e2b"
MOCK_E2B_RUNTIME_ID = "mock_e2b_python_code_sandbox:v1"


@dataclass
class SandboxExecutionResult:
    ok: bool
    backend_id: str
    runtime_id: str
    sandbox_backend: str
    sandbox_status: str
    production_ready: bool
    code_hash: str
    parent_table_ids: list[str]
    output_table_ids: list[str] = field(default_factory=list)
    outputs: dict[str, Any] | None = None
    stdout: str = ""
    stderr: str = ""
    execution_ms: int = 0
    timeout_ms: int = 0
    timed_out: bool = False
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def base_metadata(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "runtime": self.runtime_id,
            "sandbox_backend": self.sandbox_backend,
            "sandbox_status": self.sandbox_status,
            "production_ready": self.production_ready,
            "operation_kind": "python_code",
            "code_hash": self.code_hash,
            "parent_table_ids": self.parent_table_ids,
            "derived_from_table_ids": self.parent_table_ids,
            "output_table_ids": self.output_table_ids,
            "timeout_ms": self.timeout_ms,
            "execution_ms": self.execution_ms,
            "timed_out": self.timed_out,
            "stdout": self.stdout,
            "stderr": self.stderr,
            **self.metadata,
        }


class SandboxBackend(Protocol):
    backend_id: str
    runtime_id: str
    sandbox_backend: str
    sandbox_status: str
    production_ready: bool

    def run(self, payload: dict[str, Any], operation: PythonCodeOperation, code_hash: str) -> SandboxExecutionResult:
        ...


class LocalBetaSandboxBackend:
    backend_id = LOCAL_BACKEND_ID
    runtime_id = LOCAL_RUNTIME_ID
    sandbox_backend = LOCAL_SANDBOX_BACKEND
    sandbox_status = LOCAL_SANDBOX_STATUS
    production_ready = False

    def run(self, payload: dict[str, Any], operation: PythonCodeOperation, code_hash: str) -> SandboxExecutionResult:
        sandbox_exec = shutil.which("sandbox-exec")
        if sandbox_exec is None:
            return _error_result(
                self,
                operation,
                code_hash,
                code="sandbox_unavailable",
                message="python_code operations require /usr/bin/sandbox-exec on this local runtime.",
            )

        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="nba-analysis-sandbox-") as scratch:
            command = [
                sandbox_exec,
                "-p",
                _sandbox_profile(scratch),
                sys.executable,
                "-I",
                "-S",
                str(Path(__file__).with_name("sandbox_child.py")),
            ]
            try:
                completed = subprocess.run(
                    command,
                    input=json.dumps(payload),
                    text=True,
                    capture_output=True,
                    timeout=operation.policy.timeout_ms / 1000,
                    cwd=scratch,
                    env={"PYTHONNOUSERSITE": "1"},
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                return _error_result(
                    self,
                    operation,
                    code_hash,
                    code="sandbox_timeout",
                    message="python_code operation exceeded its timeout.",
                    execution_ms=int((time.monotonic() - started) * 1000),
                    stdout=exc.stdout or "",
                    stderr=exc.stderr or "",
                    timed_out=True,
                )
        return _completed_process_result(self, completed, operation, code_hash, int((time.monotonic() - started) * 1000))


class MockE2BBackend:
    backend_id = MOCK_E2B_BACKEND_ID
    runtime_id = MOCK_E2B_RUNTIME_ID
    sandbox_backend = "e2b_mock"
    sandbox_status = "mock_only"
    production_ready = False

    def run(self, payload: dict[str, Any], operation: PythonCodeOperation, code_hash: str) -> SandboxExecutionResult:
        # Deterministic tests use this backend to verify cloud-backend plumbing
        # without credentials or network calls. It deliberately executes no code.
        outputs = {"tables": [], "metrics": [], "findings": []}
        for schema in operation.output_tables:
            outputs["tables"].append(
                {
                    "id": schema.id,
                    "title": schema.title,
                    "rows": [],
                }
            )
        return SandboxExecutionResult(
            ok=True,
            backend_id=self.backend_id,
            runtime_id=self.runtime_id,
            sandbox_backend=self.sandbox_backend,
            sandbox_status=self.sandbox_status,
            production_ready=self.production_ready,
            code_hash=code_hash,
            parent_table_ids=operation.input_table_ids,
            output_table_ids=[schema.id for schema in operation.output_tables],
            outputs=outputs,
            stdout="mock_e2b executed no user code",
            timeout_ms=operation.policy.timeout_ms,
            metadata={"network_disabled": True, "mocked": True},
        )


class E2BCloudSandboxBackend:
    backend_id = E2B_BACKEND_ID
    runtime_id = E2B_RUNTIME_ID
    sandbox_backend = "e2b_cloud"
    sandbox_status = E2B_SANDBOX_STATUS
    production_ready = True

    def run(self, payload: dict[str, Any], operation: PythonCodeOperation, code_hash: str) -> SandboxExecutionResult:
        api_key = os.getenv("E2B_API_KEY")
        if not api_key:
            return _error_result(
                self,
                operation,
                code_hash,
                code="sandbox_credentials_missing",
                message="E2B backend requires E2B_API_KEY.",
                metadata={"network_disabled": True},
            )
        try:
            from e2b import Sandbox
        except Exception:
            return _error_result(
                self,
                operation,
                code_hash,
                code="sandbox_dependency_missing",
                message="E2B backend requires the e2b Python package.",
                metadata={"network_disabled": True},
            )

        sandbox = None
        started = time.monotonic()
        try:
            sandbox = Sandbox.create(
                timeout=max(30, int(operation.policy.timeout_ms / 1000) + 30),
                envs={},
                secure=True,
                allow_internet_access=False,
                metadata={"purpose": "nba_analyst_python_analysis"},
            )
            child_path = "/tmp/nba_sandbox_child.py"
            input_path = "/tmp/nba_sandbox_input.json"
            sandbox.files.write(child_path, Path(__file__).with_name("sandbox_child.py").read_text(encoding="utf-8"))
            sandbox.files.write(input_path, json.dumps(payload))
            completed = sandbox.commands.run(
                f"python3 -I -S {child_path} < {input_path}",
                timeout=operation.policy.timeout_ms / 1000,
                request_timeout=max(5.0, operation.policy.timeout_ms / 1000 + 5),
            )
            return _command_result(self, completed, operation, code_hash, int((time.monotonic() - started) * 1000))
        except Exception as exc:
            return _error_result(
                self,
                operation,
                code_hash,
                code="sandbox_execution_failed",
                message=_sanitize_vendor_error(str(exc)),
                execution_ms=int((time.monotonic() - started) * 1000),
                metadata={"network_disabled": True},
            )
        finally:
            if sandbox is not None:
                try:
                    sandbox.kill()
                except Exception:
                    pass


def sandbox_enabled() -> bool:
    return os.getenv(SANDBOX_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def selected_backend_name() -> str:
    return os.getenv(SANDBOX_BACKEND_ENV, LOCAL_BACKEND_ID).strip() or LOCAL_BACKEND_ID


def get_sandbox_backend(name: str | None = None) -> SandboxBackend:
    backend_name = name or selected_backend_name()
    if backend_name in {LOCAL_BACKEND_ID, LOCAL_SANDBOX_BACKEND}:
        return LocalBetaSandboxBackend()
    if backend_name == MOCK_E2B_BACKEND_ID:
        return MockE2BBackend()
    if backend_name == E2B_BACKEND_ID:
        return E2BCloudSandboxBackend()
    raise ValueError(f"Unknown python_code sandbox backend: {backend_name}")


def _completed_process_result(
    backend: SandboxBackend,
    completed: subprocess.CompletedProcess[str],
    operation: PythonCodeOperation,
    code_hash: str,
    execution_ms: int,
) -> SandboxExecutionResult:
    if completed.returncode != 0 and not completed.stdout:
        return _error_result(
            backend,
            operation,
            code_hash,
            code="sandbox_process_failed",
            message="python_code sandbox process failed before returning structured output.",
            execution_ms=execution_ms,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    return _decode_stdout_result(backend, completed.stdout or "", completed.stderr or "", operation, code_hash, execution_ms)


def _command_result(
    backend: SandboxBackend,
    completed: Any,
    operation: PythonCodeOperation,
    code_hash: str,
    execution_ms: int,
) -> SandboxExecutionResult:
    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")
    return _decode_stdout_result(backend, stdout, stderr, operation, code_hash, execution_ms, metadata={"network_disabled": True})


def _decode_stdout_result(
    backend: SandboxBackend,
    stdout: str,
    stderr: str,
    operation: PythonCodeOperation,
    code_hash: str,
    execution_ms: int,
    *,
    metadata: dict[str, Any] | None = None,
) -> SandboxExecutionResult:
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        return _error_result(
            backend,
            operation,
            code_hash,
            code="invalid_sandbox_output",
            message="python_code sandbox did not return JSON.",
            execution_ms=execution_ms,
            stdout=stdout,
            stderr=stderr,
            metadata=metadata,
        )
    if stderr:
        result["stderr"] = f"{result.get('stderr', '')}{stderr}"
    if not result.get("ok"):
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        return _error_result(
            backend,
            operation,
            code_hash,
            code=str(error.get("code") or "sandbox_execution_failed"),
            message=str(error.get("message") or "python_code operation failed."),
            execution_ms=execution_ms,
            stdout=str(result.get("stdout") or ""),
            stderr=str(result.get("stderr") or ""),
            metadata=metadata,
        )
    outputs = result.get("outputs")
    if not isinstance(outputs, dict):
        return _error_result(
            backend,
            operation,
            code_hash,
            code="invalid_sandbox_output",
            message="python_code operation did not return structured outputs.",
            execution_ms=execution_ms,
            stdout=str(result.get("stdout") or ""),
            stderr=str(result.get("stderr") or ""),
            metadata=metadata,
        )
    return SandboxExecutionResult(
        ok=True,
        backend_id=backend.backend_id,
        runtime_id=backend.runtime_id,
        sandbox_backend=backend.sandbox_backend,
        sandbox_status=backend.sandbox_status,
        production_ready=backend.production_ready,
        code_hash=code_hash,
        parent_table_ids=operation.input_table_ids,
        outputs=outputs,
        stdout=str(result.get("stdout") or ""),
        stderr=str(result.get("stderr") or ""),
        execution_ms=execution_ms,
        timeout_ms=operation.policy.timeout_ms,
        metadata=metadata or {},
    )


def _error_result(
    backend: SandboxBackend,
    operation: PythonCodeOperation,
    code_hash: str,
    *,
    code: str,
    message: str,
    execution_ms: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
    metadata: dict[str, Any] | None = None,
) -> SandboxExecutionResult:
    return SandboxExecutionResult(
        ok=False,
        backend_id=backend.backend_id,
        runtime_id=backend.runtime_id,
        sandbox_backend=backend.sandbox_backend,
        sandbox_status=backend.sandbox_status,
        production_ready=backend.production_ready,
        code_hash=code_hash,
        parent_table_ids=operation.input_table_ids,
        stdout=stdout,
        stderr=stderr,
        execution_ms=execution_ms,
        timeout_ms=operation.policy.timeout_ms,
        timed_out=timed_out,
        error_code=code,
        error_message=message,
        metadata=metadata or {},
    )


def _sandbox_profile(scratch: str) -> str:
    escaped = scratch.replace("\\", "\\\\").replace('"', '\\"')
    return f"""
(version 1)
(allow default)
(deny network*)
(deny file-write*)
(allow file-write* (subpath "{escaped}"))
""".strip()


def _sanitize_vendor_error(message: str) -> str:
    redacted = message.replace(os.getenv("E2B_API_KEY", ""), "[redacted]") if os.getenv("E2B_API_KEY") else message
    return redacted[:500]
