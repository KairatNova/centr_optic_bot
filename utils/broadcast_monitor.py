import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class BroadcastStatus:
    running: bool = False
    started_at: float = 0.0
    total: int = 0
    sent: int = 0
    errors: int = 0
    requested_by: Optional[int] = None
    cancel_requested: bool = False


status = BroadcastStatus()


def start(total: int, requested_by: int) -> None:
    status.running = True
    status.started_at = time.monotonic()
    status.total = total
    status.sent = 0
    status.errors = 0
    status.requested_by = requested_by
    status.cancel_requested = False


def mark_sent(ok: bool) -> None:
    if ok:
        status.sent += 1
    else:
        status.errors += 1


def request_cancel() -> None:
    status.cancel_requested = True


def finish() -> None:
    status.running = False


def snapshot() -> dict:
    elapsed = int(time.monotonic() - status.started_at) if status.started_at else 0
    return {
        "running": status.running,
        "total": status.total,
        "sent": status.sent,
        "errors": status.errors,
        "requested_by": status.requested_by,
        "cancel_requested": status.cancel_requested,
        "elapsed_seconds": elapsed,
    }
