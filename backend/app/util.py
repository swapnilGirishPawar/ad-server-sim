"""Small shared helpers: time + id generation."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone


def now_ms() -> int:
    return int(time.time() * 1000)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    u = uuid.uuid4().hex
    return f"{prefix}{u}" if prefix else u


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
