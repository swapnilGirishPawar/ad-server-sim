"""Per-run conformance-finding collector.

Validators emit a finding for every check on every response. At load volume that
is millions of rows, almost all identical. The recorder de-duplicates by
(standard, spec_section, check, severity, endpoint, scenario), keeps the first
concrete example + an occurrence count, and persists a compact, representative
set to the `findings` table at flush time.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.db import Database
from app.util import new_id, now_iso, now_ms


class FindingRecorder:
    def __init__(self, db: Database, run_id: str, *, cap: int = 2000) -> None:
        self.db = db
        self.run_id = run_id
        self.cap = cap
        self._acc: Dict[tuple, Dict[str, Any]] = {}

    def add_many(self, findings: List[Dict[str, Any]], *, request_id: Optional[str] = None,
                 scenario: str = "") -> None:
        for f in findings or []:
            key = (f.get("standard"), f.get("spec_section"), f.get("check"),
                   f.get("severity"), f.get("endpoint", ""), scenario or f.get("scenario", ""))
            slot = self._acc.get(key)
            if slot is None:
                if len(self._acc) >= self.cap:
                    continue
                self._acc[key] = {"finding": f, "count": 1, "request_id": request_id, "scenario": scenario}
            else:
                slot["count"] += 1

    @property
    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for slot in self._acc.values():
            sev = slot["finding"].get("severity", "info")
            out[sev] = out.get(sev, 0) + 1
        return out

    async def flush(self) -> int:
        rows = []
        for slot in self._acc.values():
            f = slot["finding"]
            rows.append({
                "id": new_id(), "run_id": self.run_id, "ts": now_iso(), "ts_ms": now_ms(),
                "standard": f.get("standard"), "spec_section": f.get("spec_section"),
                "check_id": f.get("check"), "severity": f.get("severity"),
                "expected": f.get("expected"), "observed": f.get("observed"),
                "endpoint": f.get("endpoint", ""),
                "scenario": slot.get("scenario") or f.get("scenario", ""),
                "request_id": slot.get("request_id"),
            })
        if rows:
            await self.db.insert_batch("findings", rows)
        return len(rows)
