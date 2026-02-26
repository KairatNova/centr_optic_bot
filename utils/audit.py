import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_LOG_PATH = Path("logs") / "audit.log"


def write_audit_event(actor_id: int, actor_role: str, action: str, details: dict[str, Any] | None = None) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "details": details or {},
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
