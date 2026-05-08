"""Line-delimited JSON sidecar process transport."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dorje_lm.errors import LMSidecarError


class SidecarProcess:
    """Own a persistent sidecar process with bounded request timeouts."""

    def __init__(self, command: Sequence[str], cwd: Path | None = None) -> None:
        if len(command) == 0:
            raise LMSidecarError("sidecar command is empty")
        self._lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None
        self._process = subprocess.Popen(
            list(command),
            cwd=str(cwd) if cwd is not None else None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._start_stderr_forwarder()

    def request(self, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        if timeout_s <= 0.0:
            raise LMSidecarError("timeout must be positive")
        with self._lock:
            return self._request_locked(payload, timeout_s)

    def close(self) -> None:
        process = self._process
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)

    def _request_locked(self, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        process = self._process
        if process.poll() is not None:
            stderr = self._read_stderr_tail()
            raise LMSidecarError(f"sidecar exited with code {process.returncode}: {stderr}")
        if process.stdin is None or process.stdout is None:
            raise LMSidecarError("sidecar pipes are unavailable")

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            process.stdin.write(line)
            process.stdin.flush()
            response_line = self._readline_with_timeout(timeout_s)
        except BrokenPipeError as exc:
            raise LMSidecarError("sidecar pipe closed") from exc

        if response_line == "":
            stderr = self._read_stderr_tail()
            raise LMSidecarError(f"sidecar closed stdout: {stderr}")
        try:
            response = json.loads(response_line)
        except json.JSONDecodeError as exc:
            raise LMSidecarError("sidecar returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise LMSidecarError("sidecar returned non-object JSON")
        return response

    def _readline_with_timeout(self, timeout_s: float) -> str:
        process = self._process
        stdout = process.stdout
        if stdout is None:
            raise LMSidecarError("sidecar stdout is unavailable")

        result: list[str] = []
        error: list[BaseException] = []

        def target() -> None:
            try:
                result.append(stdout.readline())
            except BaseException as exc:  # noqa: BLE001
                error.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout_s)
        if thread.is_alive():
            process.kill()
            raise LMSidecarError("sidecar request timed out")
        if error:
            raise LMSidecarError("sidecar stdout read failed") from error[0]
        return result[0] if result else ""

    def _start_stderr_forwarder(self) -> None:
        process = self._process
        stderr = process.stderr
        if stderr is None:
            return

        def forward() -> None:
            for line in stderr:
                sys.stderr.write(line)

        self._stderr_thread = threading.Thread(target=forward, daemon=True)
        self._stderr_thread.start()

    def _read_stderr_tail(self) -> str:
        return ""
