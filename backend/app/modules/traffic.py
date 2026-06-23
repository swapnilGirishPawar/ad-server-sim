"""Module 2 — Traffic Generator.

Drives ad requests at a target rate with bounded concurrency, over VAST and/or
OpenRTB, with randomised country/device/browser/user combinations. Successful
fills spawn detached impression -> click -> win chains (Modules 3/4) so tracking
load is realistic and doesn't stall the request pacing.

Concurrency model (the Python analogue of the spec's Worker Threads): a single
asyncio event loop + httpx.AsyncClient, gated by a semaphore, with a token-bucket
pacer. This comfortably saturates a localhost ad server.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable, Dict, List, Optional

from app.adserver.client import AdServerClient
from app.adserver.result import AdResult
from app.adserver import tracking
from app.config import Settings
from app.db import Database
from app.models import RunRequest
from app.modules import clicks, impressions
from app.modules.users import SimUser, UserPool
from app.util import new_id, now_iso, now_ms

logger = logging.getLogger("adsim.traffic")


class TrafficRunner:
    def __init__(self, client: AdServerClient, db: Database, settings: Settings) -> None:
        self.c = client
        self.db = db
        self.s = settings
        self.stats: Dict[str, Any] = {}
        self._buf_req: List[Dict[str, Any]] = []
        self._buf_evt: List[Dict[str, Any]] = []
        self._post_tasks: List[asyncio.Task] = []
        self.stop_event = asyncio.Event()

    # ---------------------------------------------------------------- helpers
    async def _load_ad_units(self) -> List[Dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT server_id, numeric_id, name, parent_id FROM seed_entities WHERE kind='ad_unit'")
        return [{"tag_id": r["numeric_id"] or r["server_id"], "publisher_id": r["parent_id"],
                 "name": r["name"]} for r in rows if (r["numeric_id"] or r["server_id"])]

    async def _load_campaign_cpm(self) -> Dict[str, Dict[str, Any]]:
        rows = await self.db.fetchall(
            "SELECT server_id, name, data_json FROM seed_entities WHERE kind='campaign'")
        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            try:
                data = json.loads(r["data_json"] or "{}")
            except json.JSONDecodeError:
                data = {}
            cpm = data.get("target_cpm") or data.get("cpm") or data.get("cpm_bid")
            if r["name"]:
                out[r["name"]] = {"id": r["server_id"], "cpm": float(cpm) if cpm else None}
        return out

    def _merge(self, req: RunRequest) -> Dict[str, Any]:
        s = self.s
        return {
            "protocols": [p.lower() for p in (req.protocols or s.protocols)],
            "rps": req.requests_per_second if req.requests_per_second is not None else s.requests_per_second,
            "concurrency": req.concurrency or s.concurrency,
            "total": req.total_requests if req.total_requests is not None else s.total_requests,
            "duration": req.duration_seconds if req.duration_seconds is not None else s.duration_seconds,
            "impression_rate": req.impression_rate if req.impression_rate is not None else s.default_impression_rate,
            "ctr": req.ctr if req.ctr is not None else s.default_ctr,
            "countries": req.countries or s.country_list,
            "devices": req.devices or s.device_list,
            "browsers": req.browsers or s.browser_list,
            "user_pool_size": req.user_pool_size or s.user_pool_size,
            "returning_ratio": req.returning_user_ratio if req.returning_user_ratio is not None else s.returning_user_ratio,
            "fire_impressions": req.fire_impressions,
            "fire_clicks": req.fire_clicks,
            "fire_wins": req.fire_wins,
        }

    # ------------------------------------------------------------------- main
    async def run(self, req: RunRequest, *, run_id: Optional[str] = None,
                  progress_cb: Optional[Callable[[Dict[str, Any]], Any]] = None,
                  ad_units: Optional[List[Dict[str, Any]]] = None,
                  user_pool: Optional[UserPool] = None,
                  kind: str = "traffic") -> Dict[str, Any]:
        cfg = self._merge(req)
        run_id = run_id or new_id("run-")
        ad_units = ad_units if ad_units is not None else await self._load_ad_units()
        campaign_cpm = await self._load_campaign_cpm()
        rng = random.Random()
        pool = user_pool or UserPool(cfg["countries"], cfg["devices"], cfg["browsers"],
                                     cfg["user_pool_size"], cfg["returning_ratio"], rng)

        self.stats = {"run_id": run_id, "requests": 0, "responses": 0, "fills": 0,
                      "no_fills": 0, "errors": 0, "impressions": 0, "clicks": 0,
                      "wins": 0, "rps_target": cfg["rps"], "started_ms": now_ms(),
                      "total_planned": cfg["total"] if cfg["duration"] <= 0 else None,
                      "duration": cfg["duration"]}

        await self.db.insert("runs", {
            "id": run_id, "kind": kind, "label": req.label or kind, "status": "running",
            "config_json": json.dumps(cfg), "summary_json": None,
            "started_at": now_iso(), "started_ms": now_ms(), "ended_at": None, "ended_ms": None})

        if not ad_units:
            msg = "No ad units found — run a seed first (POST /seed)."
            await self._finalize(run_id, error=msg)
            return {**self.stats, "error": msg}

        flusher = asyncio.create_task(self._flusher(progress_cb))
        sem = asyncio.Semaphore(cfg["concurrency"])
        interval = 1.0 / cfg["rps"] if cfg["rps"] and cfg["rps"] > 0 else 0.0
        start = time.perf_counter()
        tasks: List[asyncio.Task] = []
        i = 0

        def keep_going() -> bool:
            if self.stop_event.is_set():
                return False
            if cfg["duration"] and cfg["duration"] > 0:
                return (time.perf_counter() - start) < cfg["duration"]
            return i < cfg["total"]

        try:
            while keep_going():
                await sem.acquire()
                if not keep_going():
                    sem.release()
                    break
                if interval:
                    target = start + i * interval
                    delay = target - time.perf_counter()
                    if delay > 0:
                        await asyncio.sleep(delay)
                t = asyncio.create_task(self._one(i, cfg, ad_units, pool, campaign_cpm, rng, run_id))
                t.add_done_callback(lambda _f: sem.release())
                tasks.append(t)
                i += 1
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._post_tasks:
                await asyncio.gather(*self._post_tasks, return_exceptions=True)
        finally:
            flusher.cancel()
            await self._flush()
            summary = await self._finalize(run_id)
        if progress_cb:
            await _maybe_await(progress_cb({**self.stats, "done": True}))
        return summary

    async def _one(self, i: int, cfg: Dict[str, Any], ad_units: List[Dict[str, Any]],
                   pool: UserPool, campaign_cpm: Dict[str, Dict[str, Any]],
                   rng: random.Random, run_id: str) -> None:
        au = rng.choice(ad_units)
        user = pool.pick()
        protocol = rng.choice(cfg["protocols"])
        tag_id, pub = str(au["tag_id"]), str(au["publisher_id"] or "")

        if protocol == "ortb":
            res = await self.c.request_ortb(tag_id=tag_id, publisher_id=pub, country=user.country,
                                            device=user.device, browser=user.browser,
                                            user_id=user.user_id, ad_format=self.s_format())
        else:
            res = await self.c.request_vast(tag_id=tag_id, publisher_id=pub, device=user.device,
                                            user_id=user.user_id)

        campaign_id, cpm = self._resolve_campaign(res, campaign_cpm)
        self.stats["requests"] += 1
        if res.status_code and res.status_code < 500 and res.status_code != 0:
            self.stats["responses"] += 1
        if res.status_code == 0 or res.status_code >= 500:
            self.stats["errors"] += 1
        if res.filled:
            self.stats["fills"] += 1
        else:
            self.stats["no_fills"] += 1

        self._buf_req.append({
            "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": now_ms(),
            "protocol": protocol, "tag_id": tag_id, "publisher_id": pub, "ad_unit_id": tag_id,
            "country": user.country, "device": user.device, "browser": user.browser,
            "user_id": user.user_id, "status_code": res.status_code, "latency_ms": res.latency_ms,
            "filled": 1 if res.filled else 0, "winner_campaign": res.campaign,
            "winner_campaign_id": res.campaign_id or campaign_id,
            "winner_creative_id": res.creative_id, "price": res.price if res.price is not None else cpm,
            "no_fill_reason": res.no_fill_reason, "trace_id": res.trace_id})

        await self.db.upsert_user_counts([{
            "user_id": user.user_id, "country": user.country, "device": user.device,
            "browser": user.browser, "ms": now_ms()}])

        if res.filled:
            self._post_tasks.append(asyncio.create_task(
                self._chain(cfg, res, tag_id, pub, user, campaign_id, cpm, rng, run_id)))

    async def _chain(self, cfg: Dict[str, Any], res: AdResult, tag_id: str, pub: str,
                     user: SimUser, campaign_id: Optional[str], cpm: Optional[float],
                     rng: random.Random, run_id: str) -> None:
        price = res.price if res.price is not None else cpm
        if cfg["fire_impressions"] and impressions.should_fire(cfg["impression_rate"], rng):
            await impressions.random_delay(self.s, rng)
            evt = await impressions.fire_impression(
                self.c, self.s, run_id=run_id, result=res, tag_id=tag_id, publisher_id=pub,
                user_id=user.user_id, campaign_id=campaign_id, campaign=res.campaign, price=price)
            self._buf_evt.append(evt)
            self.stats["impressions"] += 1

            if cfg["fire_clicks"] and clicks.should_click(cfg["ctr"], rng):
                cev = await clicks.fire_click(
                    self.c, self.s, run_id=run_id, result=res, tag_id=tag_id, publisher_id=pub,
                    user_id=user.user_id, campaign_id=campaign_id, campaign=res.campaign)
                self._buf_evt.append(cev)
                self.stats["clicks"] += 1

            if cfg["fire_wins"] and price:
                win = tracking.win_url(self.s, price=price, aid=tag_id, pub=pub,
                                       trace_id=res.trace_id or new_id())
                fired = await self.c.fire(win, normalize=False)
                self._buf_evt.append({
                    "id": new_id(), "run_id": run_id, "ts": now_iso(), "ts_ms": now_ms(),
                    "type": "win", "request_id": res.trace_id, "tag_id": tag_id,
                    "publisher_id": pub, "user_id": user.user_id, "campaign_id": campaign_id,
                    "campaign": res.campaign, "price": price, "url": fired["url"],
                    "status_code": fired["status_code"], "ok": 1 if fired["ok"] else 0,
                    "note": fired.get("note"), "trace_id": res.trace_id})
                self.stats["wins"] += 1

    def s_format(self) -> str:
        return "video"

    def _resolve_campaign(self, res: AdResult, campaign_cpm: Dict[str, Dict[str, Any]]):
        if res.protocol == "vast" and res.campaign and res.campaign in campaign_cpm:
            m = campaign_cpm[res.campaign]
            return m["id"], m["cpm"]
        return res.campaign_id, res.price

    async def _flusher(self, progress_cb: Optional[Callable]) -> None:
        try:
            while True:
                await asyncio.sleep(0.3)
                await self._flush()
                if progress_cb:
                    await _maybe_await(progress_cb(dict(self.stats)))
        except asyncio.CancelledError:
            return

    async def _flush(self) -> None:
        if self._buf_req:
            batch, self._buf_req = self._buf_req, []
            await self.db.insert_batch("ad_requests", batch)
        if self._buf_evt:
            batch, self._buf_evt = self._buf_evt, []
            await self.db.insert_batch("events", batch)

    async def _finalize(self, run_id: str, error: Optional[str] = None) -> Dict[str, Any]:
        self.stats["ended_ms"] = now_ms()
        elapsed = (self.stats["ended_ms"] - self.stats["started_ms"]) / 1000.0
        self.stats["elapsed_s"] = round(elapsed, 2)
        self.stats["rps_actual"] = round(self.stats["requests"] / elapsed, 2) if elapsed > 0 else 0
        self.stats["fill_rate"] = round(self.stats["fills"] / self.stats["requests"], 4) if self.stats["requests"] else 0
        if error:
            self.stats["error"] = error
        await self.db.execute(
            "UPDATE runs SET status=?, summary_json=?, ended_at=?, ended_ms=? WHERE id=?",
            ("failed" if error else "completed", json.dumps(self.stats), now_iso(), now_ms(), run_id))
        return self.stats


async def _maybe_await(value: Any) -> None:
    if asyncio.iscoroutine(value):
        await value
