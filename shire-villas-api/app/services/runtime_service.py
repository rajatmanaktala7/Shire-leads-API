from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict

from app.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunState:
    running: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    last_summary: dict | None = None


_state = RunState()
_lock = asyncio.Lock()


def state() -> dict:
    return asdict(_state)


async def run_once(coro_factory):
    """
    Process-local duplicate-run protection.
    Railway cron may retry or a user may double-click Run Now; this prevents
    concurrent daily suites inside the same API container.
    """
    if _lock.locked():
        return {"accepted": False, "status": "ALREADY_RUNNING", "runtime": state()}

    async with _lock:
        _state.running = True
        _state.started_at = utcnow().isoformat()
        _state.last_error = None
        try:
            result = await coro_factory()
            _state.last_status = "SUCCESS"
            _state.last_summary = result
            return result
        except Exception as exc:
            _state.last_status = "FAILED"
            _state.last_error = str(exc)[:1000]
            raise
        finally:
            _state.running = False
            _state.completed_at = utcnow().isoformat()
