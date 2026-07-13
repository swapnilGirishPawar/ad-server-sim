"""Simulator REST + WebSocket API."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from app import discovery as discovery_mod
from app import report as report_mod
from app.adserver.client import AdServerClient, AdServerError
from app.config import Settings
from app.db import Database
from app.models import (
    DspConfig, FlowRequest, PublisherAdRequest, RunRequest, ScenarioRequest, SeedRequest,
)
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


@router.get("/target")
async def target(request: Request):
    """Target discovery: which SUT routes are live (read from its OpenAPI)."""
    s, _, client, _ = _state(request)
    disc = await discovery_mod.discover(s)
    client.apply_discovery(disc)
    return {"resolved_routes": client.routes, "discovery": disc}


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


@router.get("/metrics/fill")
async def m_fill(request: Request, run_id: Optional[str] = None):
    _, db, _, _ = _state(request)
    return await metrics.fill_breakdown(db, run_id)


@router.get("/metrics/findings")
async def m_findings(request: Request, run_id: Optional[str] = None):
    _, db, _, _ = _state(request)
    return await metrics.findings_summary(db, run_id)


@router.get("/metrics/scorecard")
async def m_scorecard(request: Request, run_id: Optional[str] = None):
    _, db, _, _ = _state(request)
    return (await metrics.findings_summary(db, run_id))["scorecard"]


@router.get("/metrics/reconcile")
async def m_reconcile(request: Request, run_id: Optional[str] = None, tolerance: float = 0.05):
    _, db, client, _ = _state(request)
    try:
        await client.ensure_auth()
    except AdServerError as e:
        raise HTTPException(status_code=502, detail=f"Ad server auth failed: {e}")
    return await metrics.reconcile(db, client, run_id, tolerance)


@router.get("/supply-chain")
async def supply_chain(request: Request):
    """Fetch + validate ads.txt / app-ads.txt / sellers.json from the SUT."""
    _, _, client, _ = _state(request)
    return await client.fetch_supply_files()


# --------------------------------------------------------------- report
@router.get("/report")
async def report(request: Request, run_id: Optional[str] = None):
    s, db, client, _ = _state(request)
    return await report_mod.write_report(db, s, run_id=run_id, discovery=client.discovery)


@router.get("/report/markdown", response_class=PlainTextResponse)
async def report_md(request: Request, run_id: Optional[str] = None):
    s, db, client, _ = _state(request)
    out = await report_mod.write_report(db, s, run_id=run_id, discovery=client.discovery)
    return out["markdown"]


@router.get("/report/gaps.json")
async def report_gaps(request: Request, run_id: Optional[str] = None):
    s, db, client, _ = _state(request)
    out = await report_mod.write_report(db, s, run_id=run_id, discovery=client.discovery)
    return {"scorecard": out["scorecard"], "gaps": out["gaps"], "scenarios": out["scenarios"]}


# --------------------------------------------------------------- fake DSP
@router.get("/dsp")
async def dsp_status(request: Request):
    from app.dsp import router as dsp
    s, *_ = _state(request)
    return {"endpoint_url": s.dsp_endpoint_url, "config": dsp.CONFIG, "stats": dsp.STATS}


@router.post("/dsp/config")
async def dsp_config(request: Request, cfg: DspConfig):
    from app.dsp import router as dsp
    for k, v in cfg.patch().items():
        if k in dsp.CONFIG:
            dsp.CONFIG[k] = v
    return dsp.CONFIG


# --------------------------------------------------------------- Flow B (one click)
@router.post("/flow/ortb")
async def flow_ortb(request: Request, body: FlowRequest):
    """Run ONE OpenRTB auction end-to-end: (optionally set the DSP mode) -> POST a
    spec-correct bid request to the ad server -> the ad server fans out to our mock
    DSP -> return the DSP's decision + the ad server's winning bid. Done server-side
    so the browser avoids CORS/timeout issues with the ad server."""
    import time as _time

    import httpx

    from app.adserver import ortb as ortb_mod
    from app.adserver import validators
    from app.dsp import router as dsp
    from app.util import new_id

    s, db, client, _ = _state(request)

    if body.dsp_mode:
        dsp.CONFIG["mode"] = body.dsp_mode

    tag_id = body.tag_id
    if not tag_id:
        row = await db.fetchone(
            "SELECT numeric_id, server_id FROM seed_entities WHERE kind='ad_unit' "
            "ORDER BY created_at DESC LIMIT 1")
        if row:
            tag_id = row["numeric_id"] or row["server_id"]
    if not tag_id:
        raise HTTPException(status_code=400, detail="No tag_id available — run Seed first.")

    req_id = new_id("flow-")
    bid_req = ortb_mod.build_bid_request(
        request_id=req_id, tag_id=str(tag_id), publisher_id="pub-1",
        country=body.country, device=body.device, browser="chrome",
        user_id="flow-user", bidfloor=body.bidfloor)

    reqs_before = dsp.STATS.get("requests", 0)
    path = client.routes.get("ortb_auction", "/api/b/{tag_id}").format(tag_id=tag_id)
    url = f"{s.root_base}{path}"

    status, payload, text, err = 0, None, "", None
    t0 = _time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=body.timeout_s, verify=s.verify_tls) as c:
            r = await c.post(url, params={"pub": "pub-1"}, json=bid_req)
            status, text = r.status_code, r.text
            if r.content:
                try:
                    payload = r.json()
                except ValueError:
                    payload = None
    except httpx.HTTPError as e:
        err = f"{type(e).__name__}: {e}"
    latency = round((_time.perf_counter() - t0) * 1000, 1)

    parsed = ortb_mod.parse_bid_response(status, payload)
    vres = validators.validate_bid_response(status, payload, request=bid_req,
                                            endpoint=client.routes.get("ortb_auction", ""))
    dsp_called = dsp.STATS.get("requests", 0) > reqs_before

    return {
        "tag_id": str(tag_id),
        "endpoint": url,
        "request_summary": {
            "id": req_id, "bidfloor": body.bidfloor, "device": body.device,
            "country": body.country, "format": "video 1920x1080 CTV",
        },
        "dsp": {
            "mode": dsp.CONFIG["mode"],
            "called_by_ad_server": dsp_called,
            "decision": dsp.STATS.get("last_response"),
            "request_seen": dsp.STATS.get("last_request"),
        },
        "ad_server": {
            "status": status,
            "latency_ms": latency,
            "won": bool(parsed["filled"]),
            "winner_seat": parsed.get("seat"),
            "price": parsed.get("price"),
            "adm_has_vast": bool(parsed.get("adm") and "VAST" in (parsed.get("adm") or "")),
            "dsp_nurl_chained": bool(parsed.get("nurl") and "dsp_nurl=" in (parsed.get("nurl") or "")),
            "nbr": payload.get("nbr") if isinstance(payload, dict) else None,
            "conformant": vres.conformant,
            "fail_findings": [f.to_dict() for f in vres.findings if f.severity == validators.FAIL],
            "error": err,
        },
        "raw_response": payload if isinstance(payload, dict) else (text[:4000] or None),
    }


# -------------------------------------------------- Publisher ad request tester
@router.post("/publisher-request")
async def publisher_request(request: Request, req: PublisherAdRequest):
    """Fire N IAB-compliant *publisher ad requests* (VAST tag or OpenRTB bid
    request) at the ad server for a specific publisher + ad unit, and report
    exactly what came back per request + in aggregate.

    Self-contained: serving endpoints are public, so no seeding/auth is needed —
    you supply the publisher_id + tag_id. `preview_only` builds the request(s)
    and returns them WITHOUT sending, so you can inspect the IAB shape."""
    import asyncio
    import time as _time

    from app.adserver import ortb as ortb_mod
    from app.util import new_id

    s, db, client, _ = _state(request)
    protocol = (req.protocol or "ortb").lower()
    privacy = {k: v for k, v in {
        "gdpr": req.gdpr, "gdpr_consent": req.gdpr_consent, "consent": req.gdpr_consent,
        "us_privacy": req.us_privacy, "gpp": req.gpp, "coppa": req.coppa,
    }.items() if v is not None}

    # ---- the sample request, shown in the UI so the IAB shape is visible ----
    if protocol == "vast":
        path = client.routes.get("vast_canonical", "/api/v/{tag_id}").format(tag_id=req.tag_id)
        params: Dict[str, Any] = {"pub": req.publisher_id, "w": req.width, "h": req.height,
                                  "ifa": "<per-request-uuid>"}
        if req.device in ("ctv", "tv"):
            params["devicetype"] = 3
        if req.country:
            params["country"] = req.country
        for k in ("gdpr", "gdpr_consent", "us_privacy", "gpp"):
            if privacy.get(k) is not None:
                params[k] = privacy[k]
        sample = {"method": "GET", "url": f"{s.root_base}{path}", "params": params}
    else:
        if req.custom_request:
            sample_body: Dict[str, Any] = dict(req.custom_request)
        else:
            sample_body = ortb_mod.build_bid_request(
                request_id="<per-request-id>", tag_id=req.tag_id, publisher_id=req.publisher_id,
                country=req.country, device=req.device, browser="chrome", user_id="<ifa>",
                width=req.width, height=req.height, ad_format=req.ad_format, bidfloor=req.bidfloor,
                app_mode=req.app_mode, gdpr=req.gdpr, consent=req.gdpr_consent,
                us_privacy=req.us_privacy, gpp=req.gpp, coppa=req.coppa)
        path = client.routes.get("ortb_auction", "/api/b/{tag_id}").format(tag_id=req.tag_id)
        sample = {"method": "POST", "url": f"{s.root_base}{path}",
                  "params": {"pub": req.publisher_id}, "body": sample_body}

    if req.preview_only:
        return {"protocol": protocol, "endpoint": sample["url"], "count": req.count,
                "preview": True, "sample_request": sample, "results": [], "summary": None}

    # ---- fire N requests with bounded concurrency ----
    sem = asyncio.Semaphore(req.concurrency)

    async def one(i: int) -> Dict[str, Any]:
        async with sem:
            if protocol == "vast":
                res = await client.request_vast(
                    tag_id=req.tag_id, publisher_id=req.publisher_id, device=req.device,
                    user_id=new_id("u-"), width=req.width, height=req.height,
                    country=req.country, privacy=privacy or None)
            elif req.custom_request:
                body = dict(req.custom_request)
                if req.randomize_id:
                    body["id"] = new_id("bid-")
                res = await client.request_ortb_custom(
                    tag_id=req.tag_id, publisher_id=req.publisher_id, body=body)
            else:
                res = await client.request_ortb(
                    tag_id=req.tag_id, publisher_id=req.publisher_id, country=req.country,
                    device=req.device, browser="chrome", user_id=new_id("u-"),
                    width=req.width, height=req.height, ad_format=req.ad_format,
                    bidfloor=req.bidfloor, app_mode=req.app_mode, privacy=privacy or None)
        fail_count = sum(1 for f in res.findings if f.get("severity") == "fail")
        return {"i": i + 1, "status_code": res.status_code, "latency_ms": round(res.latency_ms, 1),
                "filled": res.filled, "classification": res.classification, "price": res.price,
                "campaign": res.campaign, "creative_id": res.creative_id,
                "no_fill_reason": res.no_fill_reason, "trace_id": res.trace_id,
                "conformant": fail_count == 0, "fail_count": fail_count,
                "findings": res.findings, "raw": res.raw,
                "adm": res.adm, "win_urls": res.win_urls}

    t0 = _time.perf_counter()
    full: List[Dict[str, Any]] = list(await asyncio.gather(*[one(i) for i in range(req.count)]))
    elapsed = round((_time.perf_counter() - t0) * 1000, 1)

    # ---- aggregate (keep per-row payload light; heavy detail from one sample) ----
    row_keys = ("i", "status_code", "latency_ms", "filled", "classification", "price",
                "campaign", "creative_id", "no_fill_reason", "trace_id", "conformant", "fail_count")
    results = [{k: r[k] for k in row_keys} for r in full]

    lat = sorted(r["latency_ms"] for r in full if r["latency_ms"])
    def _pctl(p: float) -> float:
        if not lat:
            return 0.0
        k = (len(lat) - 1) * p
        lo = int(k); hi = min(lo + 1, len(lat) - 1)
        return round(lat[lo] + (lat[hi] - lat[lo]) * (k - lo), 1)

    status_hist: Dict[str, int] = {}
    for r in full:
        key = str(r["status_code"])
        status_hist[key] = status_hist.get(key, 0) + 1
    filled = sum(1 for r in full if r["filled"])
    errors = sum(1 for r in full if r["status_code"] == 0 or r["status_code"] >= 500)
    no_fill = len(full) - filled - errors
    # Conformance is only meaningful for requests that actually got a response.
    responded = [r for r in full if not (r["status_code"] == 0 or r["status_code"] >= 500)]
    conformant = sum(1 for r in responded if r["conformant"])
    summary = {
        "count": len(full), "filled": filled, "no_fill": no_fill, "errors": errors,
        "fill_rate": round(filled / len(full), 4) if full else 0.0,
        "responded": len(responded),
        "conformant": conformant, "non_conformant": len(responded) - conformant,
        "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else 0.0,
        "p95_latency_ms": _pctl(0.95), "elapsed_ms": elapsed, "status_codes": status_hist,
    }
    # Prefer a non-conformant sample so gaps are visible; else the first response.
    rep = next((r for r in full if not r["conformant"]), full[0]) if full else None
    sample_response = None if rep is None else {
        "status_code": rep["status_code"], "classification": rep["classification"],
        "price": rep["price"], "trace_id": rep["trace_id"],
        "findings": rep["findings"], "raw": rep["raw"],
    }

    # Full winning creative (untruncated) so it can be pasted into a VAST viewer,
    # plus optional server-side playback that fires the ad's trackers + win notices.
    win_row = next((r for r in full if r["filled"] and r.get("adm")), None)
    winning_vast = win_row.get("adm") if win_row else None
    playback = None
    if req.simulate_playback and win_row:
        from app.adserver import vast as vast_mod
        parsed_vast = vast_mod.parse_vast(win_row.get("adm") or "")
        targets: List[tuple] = []
        for u in parsed_vast.get("impression_urls", []):
            targets.append(("impression", u))
        for u in parsed_vast.get("tracking_event_urls", []):
            targets.append(("quartile", u))
        for u in (win_row.get("win_urls") or []):
            targets.append(("win/billing", u))
        fired: List[Dict[str, Any]] = []
        seen: set = set()
        for ev, u in targets:
            if not u or u in seen:
                continue
            seen.add(u)
            is_dsp = "/dsp/track" in u          # DSP pixels fire as-is; ad-server pixels get host/prefix-normalized
            fire_url = u
            if is_dsp and ("localhost" in u or "host.docker.internal" in u):
                # The ad server https-upgrades the creative markup (secure inventory),
                # but the LOCAL fake DSP serves plain http — downgrade so the pixel lands.
                fire_url = fire_url.replace("https://", "http://")
            res_fire = await client.fire(fire_url, normalize=not is_dsp)
            fired.append({"event": ev, "url": res_fire["url"][:220],
                          "status_code": res_fire["status_code"], "ok": bool(res_fire["ok"])})
        playback = {
            "fired": fired,
            "ok": sum(1 for f in fired if f["ok"]),
            "total": len(fired),
            "ad_server_hits": sum(1 for f in fired if f["ok"] and "/api/track/" in f["url"]),
            "advertiser_hits": sum(1 for f in fired if f["ok"] and "/dsp/track" in f["url"]),
        }

    return {"protocol": protocol, "endpoint": sample["url"], "count": req.count, "preview": False,
            "sample_request": sample, "sample_response": sample_response,
            "winning_vast": winning_vast, "playback": playback,
            "results": results, "summary": summary}


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
