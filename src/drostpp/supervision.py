"""Subprocess process-group supervision, Linux RSS/disk watchdogs, and Docker container supervision."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import threading
import time
from typing import Callable

from .budgets import compute_dir_bytes

_PR_SET_PDEATHSIG = 1


def _linux_pdeathsig_preexec() -> Callable[[], None] | None:
    if sys.platform != "linux":
        return None
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        prctl = libc.prctl
    except Exception:
        return None

    def _preexec() -> None:
        try:
            prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
        except Exception:
            pass

    return _preexec


def get_pgid_rss_mb(pgid: int) -> float:
    """Sum VmRSS in MiB across all live Linux processes belonging to pgid."""
    if pgid <= 0 or sys.platform != "linux":
        return 0.0
    total_kb = 0
    proc_root = Path("/proc")
    try:
        entries = list(os.scandir(proc_root))
    except OSError:
        return 0.0

    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            stat_text = Path(entry.path, "stat").read_text(encoding="utf-8", errors="replace")
            rparen = stat_text.rfind(")")
            if rparen == -1:
                continue
            rest = stat_text[rparen + 2 :].split()
            if len(rest) < 3:
                continue
            proc_pgrp = int(rest[2])
            if proc_pgrp != pgid:
                continue
            status_text = Path(entry.path, "status").read_text(encoding="utf-8", errors="replace")
            for line in status_text.splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        total_kb += int(parts[1])
                    break
        except (OSError, ValueError):
            continue
    return total_kb / 1024.0


def pgid_exists(pgid: int) -> bool:
    """Return True if at least one process exists in the given process group."""
    if pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def terminate_process_group(
    pgid: int,
    *,
    proc: subprocess.Popen[bytes] | None = None,
    grace_seconds: float = 2.0,
    hard_wait_seconds: float = 3.0,
) -> None:
    """Send SIGTERM to the full process group, reap direct child, and SIGKILL any stragglers."""
    if pgid <= 0:
        return

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        if proc is not None:
            try:
                proc.poll()
            except Exception:
                pass
        return
    except PermissionError:
        pass

    grace_deadline = time.monotonic() + max(0.0, grace_seconds)
    while time.monotonic() < grace_deadline:
        if proc is not None:
            proc.poll()
        if not pgid_exists(pgid):
            return
        time.sleep(0.02)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        if proc is not None:
            try:
                proc.poll()
            except Exception:
                pass
        return
    except PermissionError:
        pass

    hard_deadline = time.monotonic() + max(0.1, hard_wait_seconds)
    while time.monotonic() < hard_deadline:
        if proc is not None:
            proc.poll()
        if not pgid_exists(pgid):
            return
        time.sleep(0.02)


@dataclass(slots=True)
class SupervisedProcessResult:
    returncode: int
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    timed_out: bool
    cancelled: bool
    kill_reason: str | None
    peak_rss_mb: float
    duration_seconds: float
    pid: int
    pgid: int


class _CappedStreamReader:
    """Reads a binary stream on a background thread up to a strict byte budget."""

    def __init__(
        self,
        stream: object,
        *,
        max_bytes: int,
        on_line: Callable[[str], None] | None = None,
        log_path: Path | None = None,
    ) -> None:
        self._stream = stream
        self._max_bytes = max(1024, max_bytes)
        self._on_line = on_line
        self._log_path = log_path
        self._chunks: list[bytes] = []
        self._stored_bytes = 0
        self.truncated = False
        self._line_buf = bytearray()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float = 2.0) -> None:
        self._thread.join(timeout=timeout)

    def text(self) -> str:
        return b"".join(self._chunks).decode("utf-8", errors="replace")

    def _run(self) -> None:
        log_fp = None
        if self._log_path is not None:
            try:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                log_fp = self._log_path.open("wb")
            except OSError:
                log_fp = None
        read_fn = getattr(self._stream, "read", None)
        if read_fn is None:
            if log_fp is not None:
                log_fp.close()
            return
        try:
            while True:
                chunk = read_fn(4096)
                if not chunk:
                    break
                if self._stored_bytes < self._max_bytes:
                    remaining = self._max_bytes - self._stored_bytes
                    piece = chunk[:remaining]
                    self._chunks.append(piece)
                    self._stored_bytes += len(piece)
                    if log_fp is not None:
                        try:
                            log_fp.write(piece)
                            log_fp.flush()
                        except OSError:
                            pass
                    if len(chunk) > remaining:
                        self.truncated = True
                else:
                    self.truncated = True

                if self._on_line is not None:
                    self._feed_lines(chunk)
        except Exception:
            pass
        finally:
            if self._on_line is not None and self._line_buf:
                try:
                    self._on_line(self._line_buf.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            if log_fp is not None:
                try:
                    log_fp.close()
                except OSError:
                    pass

    def _feed_lines(self, chunk: bytes) -> None:
        self._line_buf.extend(chunk)
        while True:
            idx = self._line_buf.find(b"\n")
            if idx == -1:
                # Cap runaway line accumulation if binary/no-newline flood arrives.
                if len(self._line_buf) > 1_048_576:
                    del self._line_buf[: len(self._line_buf) - 65536]
                break
            line_bytes = bytes(self._line_buf[:idx])
            del self._line_buf[: idx + 1]
            try:
                assert self._on_line is not None
                self._on_line(line_bytes.decode("utf-8", errors="replace"))
            except Exception:
                pass


class ProcessSupervisor:
    """Runs commands in isolated process groups with wall/RSS/disk/output/cancel enforcement."""

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path | str | None = None,
        env: dict[str, str] | None = None,
        stdin_text: str | None = None,
        wall_timeout: float = 300.0,
        max_output_bytes: int = 2 * 1024 * 1024,
        max_memory_mb: int | None = None,
        max_disk_bytes: int | None = None,
        disk_watch_dir: Path | None = None,
        rlimit_fsize_bytes: int | None = None,
        grace_seconds: float = 2.0,
        cancel_event: threading.Event | None = None,
        on_spawn: Callable[[int, int], None] | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
        on_heartbeat: Callable[[], None] | None = None,
        heartbeat_interval: float = 15.0,
        stdout_log: Path | None = None,
        stderr_log: Path | None = None,
    ) -> SupervisedProcessResult:
        started = time.monotonic()
        pdeath_fn = _linux_pdeathsig_preexec()

        def _preexec() -> None:
            if pdeath_fn is not None:
                pdeath_fn()
            if rlimit_fsize_bytes is not None and rlimit_fsize_bytes > 0:
                try:
                    resource.setrlimit(
                        resource.RLIMIT_FSIZE, (rlimit_fsize_bytes, rlimit_fsize_bytes)
                    )
                except (OSError, ValueError):
                    pass

        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=_preexec,
        )

        pid = proc.pid
        try:
            pgid = os.getpgid(pid)
        except OSError:
            pgid = pid

        if on_spawn is not None:
            on_spawn(pid, pgid)

        out_reader = _CappedStreamReader(
            proc.stdout,
            max_bytes=max_output_bytes,
            on_line=on_stdout_line,
            log_path=stdout_log,
        )
        err_reader = _CappedStreamReader(
            proc.stderr,
            max_bytes=max_output_bytes,
            log_path=stderr_log,
        )
        out_reader.start()
        err_reader.start()

        if stdin_text is not None and proc.stdin is not None:
            try:
                proc.stdin.write(stdin_text.encode("utf-8", errors="replace"))
                proc.stdin.close()
            except OSError:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        timed_out = False
        cancelled = False
        kill_reason: str | None = None
        peak_rss_mb = 0.0
        last_hb = started
        last_resource_check = 0.0
        deadline = started + max(0.05, wall_timeout)

        while True:
            rc = proc.poll()
            if rc is not None:
                # Reap any lingering descendant in the process group if leader exited early.
                if pgid_exists(pgid):
                    terminate_process_group(pgid, proc=proc, grace_seconds=0.2)
                break

            now = time.monotonic()
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                kill_reason = "cancelled"
                terminate_process_group(pgid, proc=proc, grace_seconds=grace_seconds)
                break

            if now >= deadline:
                timed_out = True
                kill_reason = f"wall timeout exceeded ({wall_timeout:.1f}s)"
                terminate_process_group(pgid, proc=proc, grace_seconds=grace_seconds)
                break

            if now - last_resource_check >= 0.25:
                last_resource_check = now
                if max_memory_mb is not None and max_memory_mb > 0:
                    rss = get_pgid_rss_mb(pgid)
                    if rss > peak_rss_mb:
                        peak_rss_mb = rss
                    if rss > max_memory_mb:
                        kill_reason = f"memory limit exceeded ({rss:.1f} MiB > {max_memory_mb} MiB)"
                        terminate_process_group(pgid, proc=proc, grace_seconds=grace_seconds)
                        break

                if (
                    max_disk_bytes is not None
                    and max_disk_bytes > 0
                    and disk_watch_dir is not None
                ):
                    used_bytes = compute_dir_bytes(disk_watch_dir)
                    if used_bytes > max_disk_bytes:
                        kill_reason = (
                            f"disk limit exceeded ({used_bytes} > {max_disk_bytes} bytes)"
                        )
                        terminate_process_group(pgid, proc=proc, grace_seconds=grace_seconds)
                        break

            if on_heartbeat is not None and (now - last_hb) >= heartbeat_interval:
                last_hb = now
                on_heartbeat()

            time.sleep(0.05)

        out_reader.join(timeout=2.0)
        err_reader.join(timeout=2.0)
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass

        final_rc = proc.poll()
        if final_rc is None:
            try:
                final_rc = proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                final_rc = -9

        return SupervisedProcessResult(
            returncode=final_rc,
            stdout=out_reader.text(),
            stderr=err_reader.text(),
            stdout_truncated=out_reader.truncated,
            stderr_truncated=err_reader.truncated,
            timed_out=timed_out,
            cancelled=cancelled,
            kill_reason=kill_reason,
            peak_rss_mb=peak_rss_mb,
            duration_seconds=time.monotonic() - started,
            pid=pid,
            pgid=pgid,
        )


class DockerRunner:
    """Builds resource-capped container run invocations and reaps labeled leftover containers."""

    def __init__(self, docker_binary: str = "docker") -> None:
        self.docker_binary = docker_binary

    def build_run_argv(
        self,
        *,
        image: str,
        command: list[str],
        run_id: str,
        attempt_id: str,
        generation: int,
        container_name: str,
        memory_mb: int = 2048,
        pids_limit: int = 256,
        network: str | None = None,
        read_only: bool = False,
        mounts: list[tuple[str, str, bool]] | None = None,
        env: dict[str, str] | None = None,
        workdir: str | None = None,
    ) -> list[str]:
        argv = [
            self.docker_binary,
            "run",
            "--rm",
            "--init",
            "--name",
            container_name,
            "--memory",
            f"{memory_mb}m",
            "--memory-swap",
            f"{memory_mb}m",
            "--pids-limit",
            str(pids_limit),
            "--label",
            f"drostpp.run_id={run_id}",
            "--label",
            f"drostpp.attempt_id={attempt_id}",
            "--label",
            f"drostpp.generation={generation}",
        ]
        if network:
            argv.extend(["--network", network])
        if read_only:
            argv.append("--read-only")
        if workdir:
            argv.extend(["-w", workdir])
        for host_path, cont_path, rw in mounts or []:
            mode = "rw" if rw else "ro"
            argv.extend(["-v", f"{host_path}:{cont_path}:{mode}"])
        for k, v in (env or {}).items():
            argv.extend(["-e", f"{k}={v}"])
        argv.append(image)
        argv.extend(command)
        return argv

    def force_remove_container(self, container_id_or_name: str, timeout: float = 10.0) -> bool:
        if not container_id_or_name:
            return False
        try:
            res = subprocess.run(
                [self.docker_binary, "rm", "-f", container_id_or_name],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def reap_labeled_containers(self, run_id: str, timeout: float = 10.0) -> list[str]:
        try:
            ps = subprocess.run(
                [
                    self.docker_binary,
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=drostpp.run_id={run_id}",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if ps.returncode != 0:
            return []
        ids = [line.strip() for line in ps.stdout.splitlines() if line.strip()]
        removed: list[str] = []
        for cid in ids:
            if self.force_remove_container(cid, timeout=timeout):
                removed.append(cid)
        return removed
