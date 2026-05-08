"""Unsafe local Python execution extension."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from dorje_sdk import tool

DEFAULT_TIMEOUT_S = 10
MAX_TIMEOUT_S = 60
MAX_CODE_CHARS = 200_000
MAX_OUTPUT_CHARS = 200_000


@tool(description="Execute arbitrary local Python code. Unsafe: runs with local user permissions.")
def run_python(
    code: str,
    input_json: dict[str, object] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    cwd: str | None = None,
) -> dict[str, object]:
    """Run Python code locally and return stdout/stderr/exit metadata."""
    _validate(code, timeout_s)
    run_cwd = Path(cwd).resolve() if cwd is not None else Path.cwd()
    if not run_cwd.exists() or not run_cwd.is_dir():
        raise ValueError("cwd must be an existing directory")

    with tempfile.TemporaryDirectory(prefix="dorje_run_python_") as temp_dir:
        script_path = Path(temp_dir) / "script.py"
        input_path = Path(temp_dir) / "input.json"
        script_path.write_text(code, encoding="utf-8")
        input_path.write_text(json.dumps(input_json or {}), encoding="utf-8")

        env = dict(os.environ)
        env["DORJE_RUN_PYTHON_INPUT"] = str(input_path)
        env["DORJE_RUN_PYTHON_TEMP"] = temp_dir

        try:
            completed = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=run_cwd,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            timed_out = False
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            stdout = _decode_timeout_output(exc.stdout)
            stderr = _decode_timeout_output(exc.stderr)

    stdout, stdout_truncated = _truncate(stdout)
    stderr, stderr_truncated = _truncate(stderr)
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "cwd": str(run_cwd),
        "unsafe": True,
        "warning": "run_python executes arbitrary local code with your user permissions; this is not a sandbox",
    }


def _validate(code: str, timeout_s: int) -> None:
    if not isinstance(code, str):
        raise TypeError("code must be a string")
    if len(code) == 0:
        raise ValueError("code is empty")
    if len(code) > MAX_CODE_CHARS:
        raise ValueError("code is too large")
    if not isinstance(timeout_s, int):
        raise TypeError("timeout_s must be an integer")
    if timeout_s <= 0 or timeout_s > MAX_TIMEOUT_S:
        raise ValueError(f"timeout_s must be between 1 and {MAX_TIMEOUT_S}")


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[:MAX_OUTPUT_CHARS], True


def _decode_timeout_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
