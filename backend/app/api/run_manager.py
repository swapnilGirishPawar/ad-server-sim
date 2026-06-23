"""Coordinates background runs (traffic / scenarios) and live WebSocket updates.

One run at a time keeps the shared ad-server client and SQLite writer
uncontended; concurrent run requests get a 409. Live stats are pushed to any
connected dashboard sockets.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from app.adserver.client import AdServerClient
from app.config import Settings
from app.db import Database
from app.models import RunRequest, ScenarioRequest
from app.modules.scenarios import ScenarioEngine
from app.modules.traffic import TrafficRunner
from app.util import new_id

logger = logging.getLogger("adsim.runmgr")


class RunManager:
    def __init__(self, db: Database, client: AdServerClient, settings: Settings) -> None:
        self.db = db
        self.client = client
        self.s = settings
        self.subscribers: Set[Any] = set()
        self.active: Optional[Dict[str, Any]] = None
        self._task: Optional[asyncio.Task] = None
        self._runner: Optional[TrafficRunner] = None

    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    # --------------------------------------------------------- websockets
    async def subscribe(self, ws: Any) -> None:
        self.subscribers.add(ws)

    def unsubscribe(self, ws: Any) -> None:
        self.subscribers.discard(ws)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        dead = []
        for ws in list(self.subscribers):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.subscribers.discard(ws)

    async def _progress(self, stats: Dict[str, Any]) -> None:
        self.active = {"kind": "traffic", "stats": stats}
        await self.broadcast({"type": "progress", "stats": stats})

    # ------------------------------------------------------------- traffic
    async def start_traffic(self, req: RunRequest) -> str:
        if self.busy():
            raise RuntimeError("A run is already in progress.")
        run_id = new_id("run-")
        runner = TrafficRunner(self.client, self.db, self.s)
        self._runner = runner
        self.active = {"kind": "traffic", "run_id": run_id, "stats": {}}

        async def go() -> None:
            await self.broadcast({"type": "started", "kind": "traffic", "run_id": run_id})
            try:
                summary = await runner.run(req, run_id=run_id, progress_cb=self._progress)
                await self.broadcast({"type": "done", "kind": "traffic", "run_id": run_id, "summary": summary})
            except Exception as e:  # noqa: BLE001
                logger.exception("traffic run failed")
                await self.broadcast({"type": "error", "kind": "traffic", "run_id": run_id, "error": str(e)})
            finally:
                self.active = None

        self._task = asyncio.create_task(go())
        return run_id

    # ----------------------------------------------------------- scenarios
    async def start_scenario(self, req: ScenarioRequest) -> str:
        if self.busy():
            raise RuntimeError("A run is already in progress.")
        await self.client.ensure_auth()
        batch_id = new_id("scen-")
        engine = ScenarioEngine(self.client, self.db, self.s)
        self.active = {"kind": "scenario", "run_id": batch_id, "scenario": req.scenario}

        async def go() -> None:
            await self.broadcast({"type": "started", "kind": "scenario",
                                  "batch_id": batch_id, "scenario": req.scenario})
            try:
                results = await engine.run(req.scenario, total=req.total_requests, label=req.label)
                await self.broadcast({"type": "scenario_done", "batch_id": batch_id, "results": results})
            except Exception as e:  # noqa: BLE001
                logger.exception("scenario run failed")
                await self.broadcast({"type": "error", "kind": "scenario", "error": str(e)})
            finally:
                self.active = None

        self._task = asyncio.create_task(go())
        return batch_id

    async def stop(self) -> bool:
        if self._runner and self.busy():
            self._runner.stop_event.set()
            return True
        return False
