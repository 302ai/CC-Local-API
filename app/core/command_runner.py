from __future__ import annotations

import asyncio
import os
import signal
import sys
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    error: Optional[str]


class CommandRunner:
    """Reusable command execution helper.

    Supports:
    - Non-stream execution returning JSON-friendly stdout/stderr/error
    - Stream execution (stdout+stderr merged) with run_id-based kill/cleanup

    Notes:
    - Uses create_subprocess_shell to allow arbitrary shell commands.
    - On Windows, kill uses taskkill to terminate the process tree.
    - On Unix, kill targets the process group (requires start_new_session=True).
    """

    def __init__(self) -> None:
        self._active: Dict[str, asyncio.subprocess.Process] = {}

    def decode_output(self, data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            pass

        if sys.platform == "win32":
            try:
                return data.decode("gbk")
            except UnicodeDecodeError:
                pass

        return data.decode("utf-8", errors="replace")

    def build_env(self, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        full_env = {**os.environ, **(env or {})}
        full_env["PYTHONIOENCODING"] = "utf-8"
        full_env["PYTHONUNBUFFERED"] = "1"
        full_env["PYTHONUTF8"] = "1"
        return full_env

    async def exec_json(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = 300.0,
        max_output_chars: int = 2_000_000,
    ) -> CommandResult:
        """Execute a command and collect stdout/stderr (non-stream).

        exit_code:
        - real process return code on normal completion
        - -1 on timeout/exception (per user requirement)
        """

        is_windows = sys.platform == "win32"
        kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "env": self.build_env(env),
            "cwd": cwd,
        }
        if not is_windows:
            kwargs["start_new_session"] = True

        try:
            proc = await asyncio.create_subprocess_shell(command, **kwargs)

            try:
                out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                stdout = self.decode_output(out_b or b"")
                stderr = self.decode_output(err_b or b"")

                if max_output_chars > 0:
                    stdout = stdout[:max_output_chars]
                    stderr = stderr[:max_output_chars]

                return CommandResult(
                    exit_code=proc.returncode if proc.returncode is not None else -1,
                    stdout=stdout,
                    stderr=stderr,
                    error=None,
                )
            except asyncio.TimeoutError:
                await self._terminate_process(proc)
                return CommandResult(exit_code=-1, stdout="", stderr="", error="Command timeout")

        except Exception as e:
            return CommandResult(exit_code=-1, stdout="", stderr="", error=f"Execution error: {e}")

    async def stream(
            self,
            command: str,
            *,
            cwd: Optional[str] = None,
            env: Optional[Dict[str, str]] = None,
            timeout: Optional[float] = 300.0,
            run_id: Optional[str] = None,
            chunk_fallback: bool = True,
            heartbeat_interval: float = 5.0,  # 新增：心跳间隔
    ) -> AsyncIterator[dict]:
        """Stream command output.

        Yields dict events:
        - {"event": "start", "run_id": ..., "pid": ..., "command": ...}
        - {"event": "output", "run_id": ..., "text": ...}
        - {"event": "heartbeat", "run_id": ..., "elapsed": ...}  # 新增
        - {"event": "error", "run_id": ..., "error": ...}
        - {"event": "done", "run_id": ..., "exit_code": ...}

        stderr is merged into stdout for ordering consistency.
        """

        run_id = run_id or str(uuid.uuid4())[:8]
        is_windows = sys.platform == "win32"

        kwargs: Dict[str, Any] = {
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
            "env": self.build_env(env),
            "cwd": cwd,
        }
        if not is_windows:
            kwargs["start_new_session"] = True

        proc: Optional[asyncio.subprocess.Process] = None
        start_time = asyncio.get_event_loop().time()
        last_output_time = start_time  # 新增：记录最后输出时间

        try:
            proc = await asyncio.create_subprocess_shell(command, **kwargs)
            self._active[run_id] = proc

            yield {"event": "start", "run_id": run_id, "pid": proc.pid, "command": command}

            line_count = 0
            while True:
                current_time = asyncio.get_event_loop().time()

                if timeout:
                    elapsed = current_time - start_time
                    if elapsed > timeout:
                        yield {"event": "error", "run_id": run_id, "error": "Command timeout"}
                        break

                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
                except asyncio.TimeoutError:
                    # 检查是否需要发送心跳
                    if current_time - last_output_time >= heartbeat_interval:
                        yield {
                            "event": "heartbeat",
                            "run_id": run_id,
                            "elapsed": round(current_time - start_time, 1),
                        }
                        last_output_time = current_time  # 重置计时器

                    if chunk_fallback:
                        try:
                            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=0.2)
                        except asyncio.TimeoutError:
                            chunk = b""

                        if chunk:
                            text = self.decode_output(chunk)
                            for part in text.splitlines():
                                part = part.rstrip("\r\n")
                                if part:
                                    line_count += 1
                                    last_output_time = asyncio.get_event_loop().time()  # 更新
                                    yield {"event": "output", "run_id": run_id, "text": part}
                            continue

                    if proc.returncode is not None:
                        break
                    continue

                if not line:
                    break

                text = self.decode_output(line).rstrip("\r\n")
                if text:
                    line_count += 1
                    last_output_time = asyncio.get_event_loop().time()  # 更新
                    yield {"event": "output", "run_id": run_id, "text": text}

            if proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass

            yield {
                "event": "done",
                "run_id": run_id,
                "exit_code": proc.returncode if proc and proc.returncode is not None else -1,
                "lines": line_count,
            }

        finally:
            await self.cleanup(run_id)

    async def kill(self, run_id: str) -> bool:
        if run_id not in self._active:
            return False
        await self.cleanup(run_id)
        return True

    async def cleanup(self, run_id: str) -> None:
        proc = self._active.pop(run_id, None)
        if proc is not None:
            await self._terminate_process(proc)

    def list_active(self) -> list[dict]:
        return [
            {"run_id": rid, "pid": proc.pid, "returncode": proc.returncode}
            for rid, proc in self._active.items()
        ]

    async def _terminate_process(self, proc: asyncio.subprocess.Process, timeout: float = 5.0) -> None:
        if proc is None or proc.returncode is not None:
            return

        pid = proc.pid

        try:
            if sys.platform == "win32":
                try:
                    killer = await asyncio.create_subprocess_shell(
                        f"taskkill /PID {pid} /T /F",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await asyncio.wait_for(killer.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    proc.kill()
                except Exception:
                    proc.kill()
            else:
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGTERM)
                except Exception:
                    try:
                        proc.terminate()
                    except ProcessLookupError:
                        return

                try:
                    await asyncio.wait_for(proc.wait(), timeout=timeout)
                    return
                except asyncio.TimeoutError:
                    pass

                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        return

        finally:
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except Exception:
                pass
