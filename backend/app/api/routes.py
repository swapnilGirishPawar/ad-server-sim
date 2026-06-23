"""Simulator REST + WebSocket API."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from app.adserver.client import AdServerClient, AdServerError
from app.config import Settings
from app.db import Database
from app.models import RunRequest, ScenarioRequest, SeedRequest
from app.modules import metrics
from app.modules.seeder import Seeder

logger = logging.getLogger("adsim.api")
router = APIRouter()


def _state(request: Request):
    st = request.app.state
    return st.settings, st.db, st.client, st.run_manager


# --------------------------------------------------------------- meta
@router.get("/health")
async def health(request: Request):
    s: Settings; client: AdServerClient
    s, db, client, _ = _state(request)
    reachable = await client.ping()
    return {"ok": True, "ad_server_url": s.ad_server_url,
            "ad_server_reachable": reachable, "authenticated": bool(client.token),
            "auth_role": client.user.get("role")}


@router.get("/config")
async def config(request: Request):
    s, *_ = _state(request)
    data = s.model_dump()
    data.pop("ad_server_password", None)
    data["protocols"] = s.protocols
    return data


# --------------------------------------------------------------- actions
@router.post("/seed")
async def seed(request: Request, req: SeedRequest):
    s, db, client, _ = _state(request)
    try:
        await client.ensure_auth()
    except AdServerError as e:
        raise HTTPException(status_code=502, detail=f"Ad server auth failed: {e}")
    summary = await Seeder(client, db, s).run(req)
    return summary


@router.post("/run")
async def run(request: Request, req: RunRequest):
    _, _, _, rm = _state(request)
    if rm.busy():
        raise HTTPException(status_code=409, detail="A run is already in progress.")
    run_id = await rm.start_traffic(req)
    return {"run_id": run_id, "status": "started"}


@router.post("/scenario")
async def scenario(request: Request, req: ScenarioRequest):
    _, _, client, rm = _state(request)
    if rm.busy():
        raise HTTPException(status_code=409, detail="A run is already in progress.")
    try:
        batch_id = await rm.start_scenario(req)
    except AdServerError as e:
        raise HTTPException(status_code=502, detail=f"Ad server auth failed: {e}")
    return {"batch_id": batch_id, "status": "started"}


@router.post("/runs/stop")
async def stop_run(request: Request):
    _, _, _, rm = _state(request)
    stopped = await rm.stop()
    return {"stopped": stopped}


@router.get("/runs")
async def runs(request: Request, limit: int = 50):
    _, db, _, _ = _state(request)
    return await metrics.list_runs(db, limit)


@router.get("/runs/active")
async def active(request: Request):
    _, _, _, rm = _state(request)
    return {"busy": rm.busy(), "active": rm.active}


# --------------------------------------------------------------- metrics
@router.get("/metrics/overview")
async def m_overview(request: Request, run_id: Optional[str] = None):
    _, db, _, _ = _state(request)
    return await metrics.overview(db, run_id)


@router.get("/metrics/campaigns")
async def m_campaigns(request: Request, run_id: Optional[str] = None):
    _, db, _, _ = _state(request)
    return await metrics.campaign_metrics(db, run_id)


@router.get("/metrics/auctions")
async def m_auctions(request: Request, run_id: Optional[str] = None):
    _, db, _, _ = _state(request)
    return await metrics.auction_metrics(db, run_id)


@router.get("/metrics/timeseries")
async def m_timeseries(request: Request, run_id: Optional[str] = None, bucket_ms: int = Query(1000, ge=200)):
    _, db, _, _ = _state(request)
    return await metrics.timeseries(db, run_id, bucket_ms)


@router.get("/metrics/scenarios")
async def m_scenarios(request: Request, run_id: Optional[str] = None):
    _, db, _, _ = _state(request)
    return await metrics.scenario_results(db, run_id)


@router.get("/metrics/cross-check")
async def cross_check(request: Request):
    """Compare simulator-modelled campaign metrics with the server's own reports."""
    s, db, client, _ = _state(request)
    try:
        await client.ensure_auth()
    except AdServerError as e:
        raise HTTPException(status_code=502, detail=f"Ad server auth failed: {e}")
    sim = {c["campaign"]: c for c in await metrics.campaign_metrics(db)}
    rows = await db.fetchall("SELECT server_id, name FROM seed_entities WHERE kind='campaign'")
    out = []
    for r in rows:
        srv_stats = await client.campaign_stats(r["server_id"]) or {}
        srv_spend = await client.campaign_spend(r["server_id"]) or {}
        sm = sim.get(r["name"], {})
        out.append({
            "campaign": r["name"], "campaign_id": r["server_id"],
            "sim_impressions": sm.get("impressions", 0), "sim_clicks": sm.get("clicks", 0),
            "sim_spend": sm.get("spend", 0.0),
            "server_impressions": srv_stats.get("impressions"),
            "server_clicks": srv_stats.get("clicks"),
            "server_spend": srv_stats.get("spend") if srv_stats else srv_spend.get("spend_total"),
        })
    return out


# --------------------------------------------------------------- websocket
@router.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    rm = websocket.app.state.run_manager
    await rm.subscribe(websocket)
    try:
        if rm.active:
            await websocket.send_json({"type": "snapshot", "active": rm.active})
        while True:
            await websocket.receive_text()  # keepalive; we only push
    except WebSocketDisconnect:
        pass
    finally:
        rm.unsubscribe(websocket)
