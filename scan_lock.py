from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, cast

try:
    from config import config, ensure_dirs
except ImportError:  # pragma: no cover - package import path
    from .config import config, ensure_dirs


SCAN_LOCK_PATH = Path(config.index_dir) / "scan_full.lock"
SCAN_CANCEL_PATH = Path(config.index_dir) / "scan_full.cancel"
SCAN_LOCK_STALE_AFTER_SECONDS = 15 * 60


@dataclass(frozen=True)
class _LockProbe:
    exists: bool
    payload: dict[str, Any] | None = None
    age_seconds: float | None = None
    error: str | None = None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0 and str(pid) in completed.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _cancel_path_for_lock(lock_path: Path) -> Path:
    if lock_path == SCAN_LOCK_PATH:
        return SCAN_CANCEL_PATH
    return lock_path.with_suffix(".cancel")


def _probe_scan_lock(lock_path: Path) -> _LockProbe:
    try:
        stat = lock_path.stat()
    except FileNotFoundError:
        return _LockProbe(exists=False)
    except OSError as exc:
        return _LockProbe(exists=True, error=f"could not stat lock: {exc}")

    age_seconds = max(0.0, datetime.now().timestamp() - stat.st_mtime)
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _LockProbe(
            exists=True, age_seconds=age_seconds, error=f"could not read lock: {exc}"
        )

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return _LockProbe(
            exists=True,
            age_seconds=age_seconds,
            error=f"invalid or incomplete JSON lock: {exc.msg}",
        )
    if not isinstance(payload, dict):
        return _LockProbe(
            exists=True, age_seconds=age_seconds, error="lock payload is not an object"
        )
    return _LockProbe(
        exists=True, payload=cast(dict[str, Any], payload), age_seconds=age_seconds
    )


def _lock_pid(payload: dict[str, Any]) -> int | None:
    raw_pid = payload.get("pid")
    if isinstance(raw_pid, int):
        return raw_pid
    if not isinstance(raw_pid, str):
        return None
    try:
        return int(raw_pid)
    except ValueError:
        return None


def _lock_age_description(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "unknown age"
    return f"{age_seconds:.1f}s old"


def _remove_stale_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(
            f"Could not remove stale FileMind scan lock at {lock_path}: {exc}"
        ) from exc


def _cancel_snapshot(cancel_path: Path) -> bytes | None:
    try:
        return cancel_path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _clear_cancel_if_unchanged(cancel_path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        return
    try:
        current = cancel_path.read_bytes()
    except FileNotFoundError:
        return
    except OSError:
        return
    if current == snapshot:
        cancel_path.unlink(missing_ok=True)


def read_scan_lock(lock_path: Path | None = None) -> dict[str, Any] | None:
    path = Path(lock_path or SCAN_LOCK_PATH)
    return _probe_scan_lock(path).payload


def acquire_scan_lock(
    mode: str,
    lock_path: Path | None = None,
    *,
    stale_after_seconds: float = SCAN_LOCK_STALE_AFTER_SECONDS,
) -> dict[str, Any]:
    ensure_dirs()
    path = Path(lock_path or SCAN_LOCK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    cancel_path = _cancel_path_for_lock(path)
    initial_cancel_snapshot = _cancel_snapshot(cancel_path)
    payload = {
        "pid": os.getpid(),
        "mode": mode,
        "started_at": _now_iso(),
        "heartbeat_at": _now_iso(),
        "status": "running",
        "phase": "acquired",
        "command": " ".join(sys.argv),
    }

    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = _probe_scan_lock(path)
            if not existing.exists:
                continue
            if existing.payload is None:
                if (
                    existing.age_seconds is not None
                    and existing.age_seconds >= stale_after_seconds
                ):
                    _remove_stale_lock(path)
                    continue
                raise RuntimeError(
                    f"FileMind scan lock at {path} is unreadable or incomplete "
                    f"({existing.error or 'unknown parse error'}) and is "
                    f"{_lock_age_description(existing.age_seconds)}. Treating it as active/retryable; "
                    "retry shortly or inspect it before removing it."
                )
            pid = _lock_pid(existing.payload)
            if pid is None:
                if (
                    existing.age_seconds is not None
                    and existing.age_seconds >= stale_after_seconds
                ):
                    _remove_stale_lock(path)
                    continue
                raise RuntimeError(
                    f"FileMind scan lock at {path} does not contain a valid pid and is "
                    f"{_lock_age_description(existing.age_seconds)}. Treating it as active/retryable; "
                    "retry shortly or inspect it before removing it."
                )
            if _process_exists(pid):
                active_mode = existing.payload.get("mode", "unknown")
                raise RuntimeError(
                    f"Another FileMind {active_mode} scan is already running (pid {pid}). "
                    f"Wait for it to finish or request cooperative cancellation."
                )
            if (
                existing.age_seconds is None
                or existing.age_seconds < stale_after_seconds
            ):
                raise RuntimeError(
                    f"FileMind scan lock at {path} belongs to dead pid {pid}, but it is only "
                    f"{_lock_age_description(existing.age_seconds)}. Treating it as active/retryable "
                    "until it is old enough for safe stale cleanup."
                )
            _remove_stale_lock(path)
            continue

        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        _clear_cancel_if_unchanged(cancel_path, initial_cancel_snapshot)
        return payload


def heartbeat_scan_lock(
    *,
    lock_path: Path | None = None,
    phase: str | None = None,
    status: str = "running",
    progress: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Refresh lock metadata so operators can see live scan progress."""
    path = Path(lock_path or SCAN_LOCK_PATH)
    payload = _probe_scan_lock(path).payload
    if not payload or _lock_pid(payload) != os.getpid():
        return None
    payload["heartbeat_at"] = _now_iso()
    payload["status"] = status
    if phase:
        payload["phase"] = phase
    if progress:
        existing_progress = payload.get("progress")
        current = (
            cast(dict[str, Any], existing_progress).copy()
            if isinstance(existing_progress, dict)
            else {}
        )
        current.update(progress)
        payload["progress"] = current
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp_path, path)
    return payload


def request_scan_cancel(
    reason: str,
    *,
    requested_by: str = "operator",
    lock_path: Path | None = None,
) -> dict[str, Any]:
    """Write a cooperative cancellation request for a running scan."""
    path = Path(lock_path or SCAN_LOCK_PATH)
    cancel_path = _cancel_path_for_lock(path)
    cancel_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "requested_at": _now_iso(),
        "requested_by": requested_by,
        "reason": reason,
        "target_lock": str(path),
    }
    cancel_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def read_scan_cancel(lock_path: Path | None = None) -> dict[str, Any] | None:
    path = Path(lock_path or SCAN_LOCK_PATH)
    cancel_path = _cancel_path_for_lock(path)
    if not cancel_path.exists():
        return None
    try:
        payload = json.loads(cancel_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {"requested_at": _now_iso(), "reason": "unparseable cancel file"}
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)
    return {"requested_at": _now_iso(), "reason": str(payload)}


def clear_scan_cancel(lock_path: Path | None = None) -> None:
    path = Path(lock_path or SCAN_LOCK_PATH)
    _cancel_path_for_lock(path).unlink(missing_ok=True)


def raise_if_scan_cancel_requested(lock_path: Path | None = None) -> None:
    payload = read_scan_cancel(lock_path)
    if payload:
        reason = payload.get("reason") or "operator requested cancellation"
        requested_by = payload.get("requested_by") or "operator"
        raise RuntimeError(
            f"FileMind scan cancellation requested by {requested_by}: {reason}"
        )


def release_scan_lock(lock_path: Path | None = None) -> None:
    path = Path(lock_path or SCAN_LOCK_PATH)
    current = _probe_scan_lock(path)
    if not current.exists:
        clear_scan_cancel(path)
        return
    if current.payload and _lock_pid(current.payload) == os.getpid():
        path.unlink(missing_ok=True)
        clear_scan_cancel(path)


@contextmanager
def scan_lock(mode: str, lock_path: Path | None = None) -> Iterator[dict[str, Any]]:
    path = Path(lock_path or SCAN_LOCK_PATH)
    payload = acquire_scan_lock(mode, path)
    try:
        yield payload
    finally:
        release_scan_lock(path)
